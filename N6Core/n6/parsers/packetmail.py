# -*- coding: utf-8 -*-

# Copyright (c) 2013-2020 NASK. All rights reserved.

import sys

from n6.parsers.generic import (
    TabDataParser,
    entry_point_factory,
)
from n6lib.datetime_helpers import (
    ReactionToProblematicTime,
    parse_iso_datetime,
    datetime_with_tz_to_utc,
)
from n6lib.log_helpers import get_logger


LOGGER = get_logger(__name__)


class _PacketmailBaseParser(TabDataParser):

    skip_blank_rows = True
    ignored_row_prefixes = '#'
    field_sep = ';'

    def process_row_fields(self, data, parsed, ip, timestamp, *rest):
        parsed['address'] = {'ip': ip}
        parsed['time'] = self._convert_cet_to_utc(parse_iso_datetime(timestamp))

    @staticmethod
    def _convert_cet_to_utc(cet_date):
        return datetime_with_tz_to_utc(
            cet_date,
            'Europe/Berlin',
            on_ambiguous_time=ReactionToProblematicTime.PICK_THE_LATER,
            on_non_existent_time=ReactionToProblematicTime.PICK_THE_LATER)


class PacketmailScanningParser(_PacketmailBaseParser):

    default_binding_key = 'packetmail-net.list'
    constant_items = {
        'restriction': 'public',
        'confidence': 'low',
        'category': 'scanning',
        'origin': 'honeypot',
    }


class PacketmailRatwareParser(_PacketmailBaseParser):

    default_binding_key = 'packetmail-net.ratware-list'
    constant_items = {
        'restriction': 'public',
        'confidence': 'low',
        'category': 'spam',
        'origin': 'honeypot',
    }


class PacketmailOthersParser(_PacketmailBaseParser):

    default_binding_key = 'packetmail-net.others-list'
    constant_items = {
        'restriction': 'public',
        'confidence': 'low',
        'category': 'other',
        'origin': 'honeypot',
    }

    field_sep = '\t'

    def process_row_fields(self, data, parsed, idle1, idle2, idle3, idle4, timestamp, ip):
        parsed['address'] = {'ip': ip}
        parsed['time'] = self._convert_cet_to_utc(parse_iso_datetime(timestamp))


entry_point_factory(sys.modules[__name__])
