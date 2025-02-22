# Copyright (c) 2013-2021 NASK. All rights reserved.

"""
The *recorder* component -- adds n6 events to the Event DB.
"""

### TODO: this module is to be replaced with a new implementation...

import datetime
import logging
import os
import sys

import MySQLdb.cursors
import sqlalchemy.event
from sqlalchemy import (
    create_engine,
    text as sqla_text,
)
from sqlalchemy.exc import (
    IntegrityError,
    OperationalError,
    SQLAlchemyError,
)

from n6datapipeline.base import LegacyQueuedBase
from n6lib.common_helpers import str_to_bool
from n6lib.config import Config
from n6lib.data_backend_api import (
    N6DataBackendAPI,
    transact,
)
from n6lib.data_spec.fields import SourceField
from n6lib.datetime_helpers import parse_iso_datetime_to_utc
from n6lib.db_events import (
    n6ClientToEvent,
    n6NormalizedData,
)
from n6lib.log_helpers import (
    get_logger,
    logging_configured,
)
from n6lib.record_dict import (
    RecordDict,
    BLRecordDict,
)
from n6lib.common_helpers import (
    ascii_str,
    make_exc_ascii_str,
    replace_segment,
)


LOGGER = get_logger(__name__)

DB_WARN_LOGGER_LEGACY_NAME = 'n6.archiver.mysqldb_patch'  # TODO later: change or make configurable
DB_WARN_LOGGER = get_logger(DB_WARN_LOGGER_LEGACY_NAME)


class N6RecorderCursor(MySQLdb.cursors.Cursor):

    # Note: the places where our `__log_warnings_from_database()` method
    # is invoked are analogous to the places where appropriate warnings-
    # -related stuff was invoked by the default cursor (a client-side one)
    # provided by the version 1.3.14 of the *mysqlclient* library -- see:
    # https://github.com/PyMySQL/mysqlclient/blob/1.3.14/MySQLdb/cursors.py
    # -- which was the last version before removing the warnings-related
    # stuff from that library (now we use a newer version, without that
    # stuff).
    #
    # In practice, from the following three methods extended by us,
    # rather only `execute()` is really relevant for us (note that it is
    # also called by the `executemany()` method which, therefore, does
    # not need to be extended).

    def execute(self, query, args=None):
        ret = super(N6RecorderCursor, self).execute(query, args)
        self.__log_warnings_from_database('QUERY', query, args)
        return ret

    def callproc(self, procname, args=()):
        ret = super(N6RecorderCursor, self).callproc(procname, args)
        self.__log_warnings_from_database('PROCEDURE CALL', procname, args)
        return ret

    def nextset(self):
        ret = super(N6RecorderCursor, self).nextset()
        if ret is not None:
            self.__log_warnings_from_database('ON NEXT RESULT SET')
        return ret

    __cur_warning_count = None

    def __log_warnings_from_database(self, caption, query_or_proc=None, args=None):
        conn = self.connection
        if conn is None or not conn.warning_count():
            return
        for level, code, msg in conn.show_warnings():
            log_msg = '[{}] {} (code: {}), {}'.format(ascii_str(level),
                                                      ascii_str(msg),
                                                      ascii_str(code),
                                                      caption)
            if query_or_proc or args:
                log_msg_format = (log_msg.replace('%', '%%')
                                  + ': %a, '
                                  + 'ARGS: %a')
                DB_WARN_LOGGER.warning(log_msg_format, query_or_proc, args)
            else:
                DB_WARN_LOGGER.warning(log_msg)


class Recorder(LegacyQueuedBase):
    """Save record in zbd queue."""

    _MIN_WAIT_TIMEOUT = 3600
    _MAX_WAIT_TIMEOUT = _DEFAULT_WAIT_TIMEOUT = 28800

    input_queue = {
        "exchange": "event",
        "exchange_type": "topic",
        "queue_name": "zbd",
        "accepted_event_types": [
            "event",
            "bl-new",
            "bl-change",
            "bl-delist",
            "bl-expire",
            "bl-update",
            "suppressed",
        ],
    }

    output_queue = {
        "exchange": "event",
        "exchange_type": "topic",
    }

    def __init__(self, **kwargs):
        LOGGER.info("Recorder Start")
        config = Config(required={"recorder": ("uri",)})
        self.config = config["recorder"]
        self.record_dict = None
        self.records = None
        self.routing_key = None
        self.session_db = self._setup_db()
        self.dict_map_fun = {
            "event.filtered": (RecordDict.from_json, self.new_event),
            "bl-new.filtered": (BLRecordDict.from_json, self.blacklist_new),
            "bl-change.filtered": (BLRecordDict.from_json, self.blacklist_change),
            "bl-delist.filtered": (BLRecordDict.from_json, self.blacklist_delist),
            "bl-expire.filtered": (BLRecordDict.from_json, self.blacklist_expire),
            "bl-update.filtered": (BLRecordDict.from_json, self.blacklist_update),
            "suppressed.filtered": (RecordDict.from_json, self.suppressed_update),
        }
        # keys in each of the tuples being values of `dict_map_fun`
        self.FROM_JSON = 0
        self.HANDLE_EVENT = 1
        super(Recorder, self).__init__(**kwargs)

    def _setup_db(self):
        wait_timeout = int(self.config.get("wait_timeout", self._DEFAULT_WAIT_TIMEOUT))
        wait_timeout = min(max(wait_timeout, self._MIN_WAIT_TIMEOUT), self._MAX_WAIT_TIMEOUT)
        # (`pool_recycle` should be significantly less than `wait_timeout`)
        pool_recycle = wait_timeout // 2
        engine = create_engine(
            self.config["uri"],
            connect_args=dict(
                charset=self.config.get(
                    "connect_charset",
                    N6DataBackendAPI.EVENT_DB_LEGACY_CHARSET),
                use_unicode=True,
                binary_prefix=True,
                cursorclass=N6RecorderCursor),
            pool_recycle=pool_recycle,
            echo=str_to_bool(self.config.get("echo", "false")))
        self._install_session_variables_setter(
            engine,
            wait_timeout=wait_timeout,
            time_zone="'+00:00'")
        session_db = N6DataBackendAPI.configure_db_session(engine)
        session_db.execute(sqla_text("SELECT 1"))  # Let's crash early if db is misconfigured.
        return session_db

    def _install_session_variables_setter(self, engine, **session_variables):
        setter_sql = 'SET ' + ' , '.join(
            'SESSION {} = {}'.format(name, value)
            for name, value in session_variables.items())

        @sqlalchemy.event.listens_for(engine, 'connect')
        def set_session_variables(dbapi_connection, connection_record):
            """
            Execute
            "SET SESSION <var1> = <val1>, SESSION <var2> = <val2>, ..."
            to set the specified variables.

            To be called automatically whenever a new low-level
            connection to the database is established.

            WARNING: for simplicity, the variable names and values are
            inserted "as is", *without* any escaping -- we assume we
            can treat them as *trusted* data.
            """
            with dbapi_connection.cursor() as cursor:
                cursor.execute(setter_sql)

    @classmethod
    def get_arg_parser(cls):
        parser = super(Recorder, cls).get_arg_parser()
        parser.add_argument("--n6recorder-blacklist", type=SourceField().clean_result_value,
                            help="the identifier of a blacklist source (in the "
                                 "format: 'source-label.source-channel'); if given, "
                                 "this recorder instance will consume and store "
                                 "*only* events from this blacklist source")
        parser.add_argument("--n6recorder-non-blacklist", action="store_true",
                            help="if given, this recorder instance will consume "
                                 "and store *only* events from *all* non-blacklist "
                                 "sources (note: then the '--n6recorder-blacklist' "
                                 "option, if given, is just ignored)")
        return parser

    def ping_connection(self):
        """
        Required to maintain the connection to MySQL.
        Perform ping before each query to the database.
        OperationalError if an exception occurs, remove sessions, and connects again.
        """
        try:
            self.session_db.execute(sqla_text("SELECT 1"))
        except OperationalError as exc:
            # OperationalError: (2006, 'MySQL server has gone away')
            LOGGER.warning("Database server went away: %a", exc)
            LOGGER.info("Reconnect to server")
            self.session_db.remove()
            try:
                self.session_db.execute(sqla_text("SELECT 1"))
            except SQLAlchemyError as exc:
                LOGGER.error(
                    "Could not reconnect to the MySQL database: %s",
                    make_exc_ascii_str(exc))
                sys.exit(1)

    @staticmethod
    def get_truncated_rk(rk, parts):
        """
        Get only a part of the given routing key.

        Args:
            `rk`: routing key.
            `parts`: number of dot-separated parts (segments) to be kept.

        Returns:
            Truncated `rk` (containing only first `parts` segments).

        >>> Recorder.get_truncated_rk('111.222.333.444', 0)
        ''
        >>> Recorder.get_truncated_rk('111.222.333.444', 1)
        '111'
        >>> Recorder.get_truncated_rk('111.222.333.444', 2)
        '111.222'
        >>> Recorder.get_truncated_rk('111.222.333.444', 3)
        '111.222.333'
        >>> Recorder.get_truncated_rk('111.222.333.444', 4)
        '111.222.333.444'
        >>> Recorder.get_truncated_rk('111.222.333.444', 5)  # with log warning
        '111.222.333.444'
        """
        rk = rk.split('.')
        parts_rk = []
        try:
            for i in range(parts):
                parts_rk.append(rk[i])
        except IndexError:
            LOGGER.warning("routing key %a contains less than %a segments", rk, parts)
        return '.'.join(parts_rk)

    def input_callback(self, routing_key, body, properties):
        """ Channel callback method """
        # first let's try ping mysql server
        self.ping_connection()
        self.records = {'event': [], 'client': []}
        self.routing_key = routing_key

        # take the first two parts of the routing key
        truncated_rk = self.get_truncated_rk(self.routing_key, 2)

        # run BLRecordDict.from_json() or RecordDict.from_json()
        # depending on the routing key
        from_json = self.dict_map_fun[truncated_rk][self.FROM_JSON]
        self.record_dict = from_json(body)
        # add modified time, set microseconds to 0, because the database
        #  does not have microseconds, and it is not known if the base is not rounded
        self.record_dict['modified'] = datetime.datetime.utcnow().replace(microsecond=0)
        # run the handler method corresponding to the routing key
        handle_event = self.dict_map_fun[truncated_rk][self.HANDLE_EVENT]
        with self.setting_error_event_info(self.record_dict):
            handle_event()

        assert 'source' in self.record_dict
        LOGGER.debug("source: %a", self.record_dict['source'])
        LOGGER.debug("properties: %a", properties)
        #LOGGER.debug("body: %a", body)

    def json_to_record(self, rows):
        """
        Deserialize json to record db.append.

        Args: `rows`: row from RecordDict
        """
        if 'client' in rows[0]:
            for client in rows[0]['client']:
                tmp_rows = rows[0].copy()
                tmp_rows['client'] = client
                self.records['client'].append(tmp_rows)

    def insert_new_event(self, items, with_transact=True, recorded=False):
        """
        New events and new blacklist add to database,
        default in the transaction, or the outer transaction(with_transact=False).
        """
        try:
            if with_transact:
                with transact:
                    self.session_db.add_all(items)
            else:
                assert transact.is_entered
                self.session_db.add_all(items)
        except IntegrityError as exc:
            str_exc = make_exc_ascii_str(exc)
            LOGGER.warning(str_exc)
        else:
            if recorded and not self.cmdline_args.n6recovery:
                rk = replace_segment(self.routing_key, 1, 'recorded')
                LOGGER.debug(
                    'Publish for email notifications '
                    '-- rk: %a, record_dict: %a',
                    rk, self.record_dict)
                self.publish_event(self.record_dict, rk)

    def publish_event(self, data, rk):
        """
        Publishes event to the output queue.

        Args:
            `data`: data from recorddict
            `rk`  : routing key
        """
        body = data.get_ready_json()
        self.publish_output(routing_key=rk, body=body)

    def new_event(self, _is_blacklist=False):
        """
        Add new event to n6 database.
        """
        LOGGER.debug('* new_event() %a', self.record_dict)

        # add event records from RecordDict
        for event_record in self.record_dict.iter_db_items():
            if _is_blacklist:
                event_record["status"] = "active"
            self.records['event'].append(event_record)

        self.json_to_record(self.records['event'])
        items = []
        for record in self.records['event']:
            event = n6NormalizedData(**record)
            items.append(event)

        for record in self.records['client']:
            client = n6ClientToEvent(**record)
            items.append(client)

        LOGGER.debug("insert new events, count.: %a", len(items))
        self.insert_new_event(items, recorded=True)

    def blacklist_new(self):
        self.new_event(_is_blacklist=True)

    def blacklist_change(self):
        """
        Black list change(change status to replaced in existing blacklist event,
        and add new event in changing values(new id, and old replaces give comparator)).
        """
        # add event records from RecordDict
        for event_record in self.record_dict.iter_db_items():
            self.records['event'].append(event_record)

        self.json_to_record(self.records['event'])
        id_db = self.records['event'][0]["id"]
        id_replaces = self.records['event'][0]["replaces"]
        LOGGER.debug("ID: %a REPLACES: %a", id_db, id_replaces)

        try:
            with transact:
                rec_count = (self.session_db.query(n6NormalizedData).
                             filter(n6NormalizedData.id == id_replaces).
                             update({'status': 'replaced',
                                     'modified': datetime.datetime.utcnow().replace(microsecond=0)
                                     }))

            with transact:
                items = []
                for record in self.records['event']:
                    record["status"] = "active"
                    event = n6NormalizedData(**record)
                    items.append(event)

                for record in self.records['client']:
                    client = n6ClientToEvent(**record)
                    items.append(client)

                if rec_count:
                    LOGGER.debug("insert new events, count.: %a", len(items))
                else:
                    LOGGER.debug("bl-change, records with id %a DO NOT EXIST!", id_replaces)
                    LOGGER.debug("inserting new events anyway, count.: %a", len(items))
                self.insert_new_event(items, with_transact=False, recorded=True)

        except IntegrityError as exc:
            LOGGER.warning("IntegrityError: %a", exc)

    def blacklist_delist(self):
        """
        Black list delist (change status to delisted in existing blacklist event).
        """
        # add event records from RecordDict
        for event_record in self.record_dict.iter_db_items():
            self.records['event'].append(event_record)

        self.json_to_record(self.records['event'])
        id_db = self.records['event'][0]["id"]
        LOGGER.debug("ID: %a STATUS: %a", id_db, 'delisted')

        with transact:
            (self.session_db.query(n6NormalizedData).
             filter(n6NormalizedData.id == id_db).
             update(
                {
                    'status': 'delisted',
                    'modified': datetime.datetime.utcnow().replace(microsecond=0),
                }))

    def blacklist_expire(self):
        """
        Black list expire (change status to expired in existing blacklist event).
        """
        # add event records from RecordDict
        for event_record in self.record_dict.iter_db_items():
            self.records['event'].append(event_record)

        self.json_to_record(self.records['event'])

        id_db = self.records['event'][0]["id"]
        LOGGER.debug("ID: %a STATUS: %a", id_db, 'expired')

        with transact:
            (self.session_db.query(n6NormalizedData).
             filter(n6NormalizedData.id == id_db).
             update(
                {
                    'status': 'expired',
                    'modified': datetime.datetime.utcnow().replace(microsecond=0),
                }))

    def blacklist_update(self):
        """
        Black list update (change expires to new value in existing blacklist event).
        """
        # add event records from RecordDict
        for event_record in self.record_dict.iter_db_items():
            self.records['event'].append(event_record)

        self.json_to_record(self.records['event'])
        id_event = self.records['event'][0]["id"]
        expires = self.records['event'][0]["expires"]
        LOGGER.debug("ID: %a NEW_EXPIRES: %a", id_event, expires)

        with transact:
            rec_count = (self.session_db.query(n6NormalizedData).
                         filter(n6NormalizedData.id == id_event).
                         update({'expires': expires,
                                 'modified': datetime.datetime.utcnow().replace(microsecond=0),
                                 }))
            if rec_count:
                LOGGER.debug("records with the same id %a exist: %a",
                             id_event, rec_count)
            else:
                items = []
                for record in self.records['event']:
                    record["status"] = "active"
                    event = n6NormalizedData(**record)
                    items.append(event)

                for record in self.records['client']:
                    client = n6ClientToEvent(**record)
                    items.append(client)
                LOGGER.debug("bl-update, records with id %a DO NOT EXIST!", id_event)
                LOGGER.debug("insert new events,::count:: %a", len(items))
                self.insert_new_event(items, with_transact=False)

    def suppressed_update(self):
        """
        Agregated event update(change fields: until and count, to the value of  suppressed event).
        """
        LOGGER.debug('* suppressed_update() %a', self.record_dict)

        # add event records from RecordDict
        for event_record in self.record_dict.iter_db_items():
            self.records['event'].append(event_record)

        self.json_to_record(self.records['event'])
        id_event = self.records['event'][0]["id"]
        until = self.records['event'][0]["until"]
        count = self.records['event'][0]["count"]

        # optimization: we can limit time => searching within one partition, not all;
        # it seems that mysql (and/or sqlalchemy?) truncates times to seconds,
        # we are also not 100% sure if other time data micro-distortions are not done
        # -- that's why here we use a 1-second-range instead of an exact value
        first_time_min = parse_iso_datetime_to_utc(
            self.record_dict["_first_time"]).replace(microsecond=0)
        first_time_max = first_time_min + datetime.timedelta(days=0, seconds=1)

        with transact:
            rec_count = (self.session_db.query(n6NormalizedData)
                         .filter(
                             n6NormalizedData.time >= first_time_min,
                             n6NormalizedData.time <= first_time_max,
                             n6NormalizedData.id == id_event)
                         .update({'until': until, 'count': count}))
            if rec_count:
                LOGGER.debug("records with the same id %a exist: %a",
                             id_event, rec_count)
            else:
                items = []
                for record in self.records['event']:
                    event = n6NormalizedData(**record)
                    items.append(event)

                for record in self.records['client']:
                    client = n6ClientToEvent(**record)
                    items.append(client)
                LOGGER.warning("suppressed_update, records with id %a DO NOT EXIST!", id_event)
                LOGGER.debug("insert new events,,::count:: %a", len(items))
                self.insert_new_event(items, with_transact=False)


def main():
    parser = Recorder.get_arg_parser()
    args = Recorder.parse_only_n6_args(parser)
    if args.n6recorder_non_blacklist:
        monkey_patch_non_bl_recorder()
    elif args.n6recorder_blacklist is not None:
        monkey_patch_bl_recorder(args.n6recorder_blacklist)
    with logging_configured():
        if os.environ.get('n6integration_test'):
            # for debugging only
            LOGGER.setLevel(logging.DEBUG)
            LOGGER.addHandler(logging.StreamHandler(stream=sys.__stdout__))
        d = Recorder()
        try:
            d.run()
        except KeyboardInterrupt:
            d.stop()


def monkey_patch_non_bl_recorder():
    Recorder.input_queue = {
        "exchange": "event",
        "exchange_type": "topic",
        "queue_name": 'zbd-non-blacklist',
        "binding_keys": [
            'event.filtered.*.*',
            'suppressed.filtered.*.*',
        ]
    }


def monkey_patch_bl_recorder(source):
    Recorder.input_queue = {
        "exchange": "event",
        "exchange_type": "topic",
        "queue_name": 'zbd-bl-{}'.format(source.replace(".", "-")),
        "binding_keys": [
            x.format(source) for x in [
                'bl-new.filtered.{}',
                'bl-change.filtered.{}',
                'bl-delist.filtered.{}',
                'bl-expire.filtered.{}',
                'bl-update.filtered.{}',
            ]
        ]
    }


if __name__ == "__main__":
    main()
