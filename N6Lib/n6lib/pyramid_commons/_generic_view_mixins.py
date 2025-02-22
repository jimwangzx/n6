# Copyright (c) 2021 NASK. All rights reserved.

from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    FrozenSet,
    Iterable,
    Optional,
    Union,
)

from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPForbidden

from n6lib.auth_api import (
    AuthAPI,
    RESOURCE_ID_TO_ACCESS_ZONE,
)
from n6lib.auth_db.api import (
    AuthDatabaseAPILookupError,
    AuthManageAPI,
)
from n6lib.class_helpers import attr_required
from n6lib.common_helpers import ascii_str
from n6lib.config import Config
from n6lib.data_backend_api import N6DataBackendAPI
from n6lib.log_helpers import get_logger
from n6lib.mail_notices_api import MailNoticesAPI
from n6lib.rt_client_api import RTClientAPI
from n6lib.typing_helpers import (
    AccessInfo,
    AuthData,
    ExcFactory,
    KwargsDict,
    String,
)
from n6sdk.data_spec import BaseDataSpec
from n6sdk.data_spec.fields import Field
from n6sdk.data_spec.utils import cleaning_kwargs_as_params_with_data_spec
from n6sdk.exceptions import ParamValueCleaningError


LOGGER = get_logger(__name__)


#
# Private (module-local-only) helpers
#

_APIS_MIXIN_CLASS_NAME = 'EssentialAPIsViewMixin'

def _api_property(api_name):

    def getter(self):
        api = getattr(self.request.registry, api_name)
        if api is None:
            raise RuntimeError(
                'the {!a} view cannot make use of `{}` because it was '
                'not specified (or was specified as `None`) when the '
                'web app object was being configured'.format(
                    self,
                    ascii_str(api_name)))
        return api

    getter.__name__ = api_name
    getter.__qualname__ = '{}.{}'.format(_APIS_MIXIN_CLASS_NAME, api_name)

    return property(getter)


#
# Actual mixins provided by this module
#

class EssentialAPIsViewMixin(object):

    data_backend_api = _api_property('data_backend_api')   # type: N6DataBackendAPI

    auth_manage_api = _api_property('auth_manage_api')     # type: AuthManageAPI
    mail_notices_api = _api_property('mail_notices_api')   # type: MailNoticesAPI
    rt_client_api = _api_property('rt_client_api')         # type: RTClientAPI

    # (to be removed when we will get gid of AuthAPI)
    auth_api = _api_property('auth_api')                   # type: AuthAPI

    @property
    def org_id(self):
        # type: () -> String                   # raises `HTTPForbidden` if no user is authenticated
        return self.auth_data['org_id']

    @property
    def user_id(self):  # (aka user's *login*)
        # type: () -> String                   # raises `HTTPForbidden` if no user is authenticated
        return self.auth_data['user_id']

    @property
    def auth_data(self):
        # type: () -> AuthData                 # raises `HTTPForbidden` if no user is authenticated
        # noinspection PyUnresolvedReferences
        auth_data = self.auth_data_or_none
        if not auth_data:
            raise HTTPForbidden(u'Access not allowed.')
        return auth_data

    @property
    def auth_data_or_none(self):
        # type: () -> Optional[AuthData]
        # noinspection PyUnresolvedReferences
        return self.request.auth_data or None

    def is_event_data_resource_available(self, access_info, resource_id):
        # type: (Optional[AccessInfo], String) -> bool
        assert resource_id in RESOURCE_ID_TO_ACCESS_ZONE
        access_zone = RESOURCE_ID_TO_ACCESS_ZONE[resource_id]
        if (access_info is None
              or resource_id not in access_info['rest_api_resource_limits']
              or not access_info['access_zone_conditions'].get(access_zone)):
            return False
        # Note: the result of the following `.get_user_ids_to_org_ids()`
        # call might be cached by `auth_api`. *We want that* because we
        # want that result to be in sync with the rest of the (cached)
        # authorization information from `auth_api` -- in particular, to
        # avoid granting to a user any undue access to event data that
        # were designated to be accessible to the present organization
        # of the user during the period when the user was blocked, or
        # when some user with this user's present login (user id)
        # belonged to another organization (these cases, especially the
        # latter, would be quite hypothetical but not impossible).
        nonblocked_user_org_mapping = self.auth_api.get_user_ids_to_org_ids()
        return (nonblocked_user_org_mapping.get(self.user_id) == self.org_id)

    def send_mail_notice_to_user(self,

                                 # A user login (aka *user_id*) or a non-empty collection of such.
                                 login,         # type: Union[String, Iterable[String]]

                                 # A possible key in a dict being the value of the config option
                                 # `mail_notices_api.notice_key_to_lang_to_mail_components`.
                                 notice_key,    # type: String

                                 # Custom items (additional to those from
                                 # `AuthManageAPI.get_user_and_org_basic_info()`)
                                 # to be placed in the `data_dict` to be passed
                                 # to the e-mail message content renderer.
                                 **custom_notice_data):
        # type: (...) -> bool

        login_seq = [login] if isinstance(login, str) else list(login)
        if not login_seq:
            raise ValueError('at least one user login must be given')

        sent_to_anyone = False
        with self.mail_notices_api.dispatcher(notice_key,
                                              suppress_and_log_smtp_exc=True) as dispatch:
            for user_login in login_seq:
                if self.auth_manage_api.is_user_blocked(user_login):
                    LOGGER.error('Cannot send a %a mail notice to the '
                                 'user %a because that user is blocked!',
                                 notice_key, user_login)
                    continue
                try:
                    basic_info = self.auth_manage_api.get_user_and_org_basic_info(user_login)
                except AuthDatabaseAPILookupError:
                    LOGGER.error('Cannot send a %a mail notice to the '
                                 'user %a because that user does not exist!',
                                 notice_key, user_login)
                else:
                    notice_data = {}
                    notice_data.update(basic_info)
                    notice_data.update(custom_notice_data)
                    notice_data.update(user_login=user_login)
                    assert set(notice_data) >= {'user_login', 'org_id', 'org_actual_name', 'lang'}
                    lang = notice_data['lang']
                    assert lang is None or isinstance(lang, str) and len(lang) == 2
                    ok_recipients, _ = dispatch(user_login, notice_data, lang)
                    sent_to_anyone = sent_to_anyone or bool(ok_recipients)
        return sent_to_anyone

assert (EssentialAPIsViewMixin.__name__ == _APIS_MIXIN_CLASS_NAME
        and EssentialAPIsViewMixin.__qualname__ == _APIS_MIXIN_CLASS_NAME)


class ConfigFromPyramidSettingsViewMixin(object):

    @classmethod
    @attr_required('config_spec')
    def concrete_view_class(cls, **kwargs):
        assert cls.config_spec is not None
        pyramid_configurator = kwargs['pyramid_configurator']  # type: Configurator
        # noinspection PyUnresolvedReferences
        view_class = super(ConfigFromPyramidSettingsViewMixin, cls).concrete_view_class(**kwargs)
        view_class.config_full = view_class.prepare_config_full(pyramid_configurator)
        assert view_class.config_full is not None
        return view_class

    # The following class attribute *needs* to be set in subclasses.
    config_spec = None     # type: ClassVar[Optional[str]]

    # The following class attribute is to be set automatically (see
    # above...) -- it *can be used* by concrete view classes.
    config_full = None     # type: ClassVar[Optional[Config]]

    # The following hooks are to be invoked automatically on concrete
    # class creation; they can be extended (with `super()`) in subclasses.

    @classmethod
    def prepare_config_full(cls, pyramid_configurator):
        # type: (Configurator) -> Config
        config_constructor_kwargs = cls.prepare_config_constructor_kwargs(pyramid_configurator)
        return Config(cls.config_spec, **config_constructor_kwargs)

    @classmethod
    def prepare_config_constructor_kwargs(cls, pyramid_configurator):
        # type: (Configurator) -> KwargsDict
        config_constructor_kwargs = {
            'settings': pyramid_configurator.registry.settings,
        }
        custom_converters = cls.prepare_config_custom_converters()
        if custom_converters:
            config_constructor_kwargs['custom_converters'] = custom_converters
        return config_constructor_kwargs

    @classmethod
    def prepare_config_custom_converters(cls):
        # type: () -> Dict[str, Callable[[str], Any]]
        return {}


class WithDataSpecsViewMixin(object):

    @classmethod
    def concrete_view_class(cls, **kwargs):
        # noinspection PyUnresolvedReferences
        view_class = super(WithDataSpecsViewMixin, cls).concrete_view_class(**kwargs)
        view_class.field_specs = view_class.prepare_field_specs()
        view_class.data_specs = view_class.prepare_data_specs()
        return view_class

    # The following attribute will be set **automatically** to the
    # result of invocation of `prepare_field_specs()` (performed when a
    # concrete view class is created by the `N6ConfigHelper` stuff...).
    # The reason this attribute exists is so that there is one place --
    # a concrete implementation of the `prepare_field_specs() method
    # (whose abstract stuff is defined below) -- where all needed *data
    # spec fields* are defined, so that any *data specs* defined in
    # subclasses can just refer to them (avoiding repeating data spec
    # field definitions).
    field_specs = None     # type: Dict[str, Field]

    # The following attribute will be set **automatically** to the
    # result of invocation of `prepare_data_specs()` (performed when a
    # concrete view class is created by the `N6ConfigHelper` stuff...).
    # For more information, see the docs of the `prepare_data_specs()`
    # method (defined below).
    data_specs = None      # type: Dict[str, BaseDataSpec]

    #
    # Hooks that can be extended (with `super()`) in subclasses

    @classmethod
    def prepare_field_specs(cls):
        # type: () -> Dict[str, Field]
        """
        Return a dict whose items are data spec *fields* (instances
        of `Field` subclasses) -- to be used by *data spec(s)* of a
        particular concrete view.  Invocation of this method is
        automatic (performed when a concrete view class is created by
        the `N6ConfigHelper` stuff...); the resultant dict is set as the
        value of the `field_specs` attribute of the concrete view class.

        Note: the default implementation returns an empty dict -- so you
        may want to extend/override this method in your view subclasses.
        """
        return {}

    @classmethod
    def prepare_data_specs(cls):
        # type: () -> Dict[str, BaseDataSpec]
        """
        Return  a dict whose items are *data specs* (instances of
        `BaseDataSpec` or of its subclasses) -- to be used by a
        particular concrete view.  Invocation of this method is
        automatic (performed when a concrete view class is created by
        the `N6ConfigHelper` stuff...); the resultant dict instance is
        set as the value of the `data_specs` attribute of the concrete
        view class.

        Note: the default implementation returns an empty dict -- so you
        may want to extend/override this method in your view subclasses.
        Typically, in your implementations of this method, you will want
        to make use of the `make_data_spec()` utility method; also, most
        probably, you will refer to items of the `cls.field_specs` dict.
        """
        return {}

    #
    # Helper methods -- to be used in subclasses

    @classmethod
    def make_data_spec(cls, **name_to_field):
        # type: (**Field) -> BaseDataSpec
        """
        Make a new *data spec* (an instance of a `BaseDataSpec` subclass).

        The keyword arguments (*kwargs*) should define the fields of the
        to-be-created data spec: argument names should be field names,
        and argument values should be field objects (i.e., instances of
        `Field`'s subclasses).
        """
        # noinspection PyPep8Naming
        class data_spec_class(BaseDataSpec):
            """A data spec class generated with a view's `make_data_spec()`."""

        data_spec_class.__module__ = cls.__module__
        data_spec_class.__name__ = 'data_spec_made_by_{}'.format(cls.__name__)
        data_spec_class.__qualname__ = '{}.{}'.format(cls.__qualname__, data_spec_class.__name__)

        for field_name, field in sorted(name_to_field.items()):
            setattr(data_spec_class, field_name, field)

        data_spec = data_spec_class()
        return data_spec


class WithDataSpecsAlsoForRequestParamsViewMixin(WithDataSpecsViewMixin):

    #
    # Extended `AbstractViewBase`'s hooks

    @classmethod
    def concrete_view_class(cls, **kwargs):
        # noinspection PyUnresolvedReferences
        view_class = super(WithDataSpecsAlsoForRequestParamsViewMixin,
                           cls).concrete_view_class(**kwargs)
        # noinspection PyProtectedMember
        view_class._provide_clean_request_params_method()
        return view_class

    def prepare_params(self):
        # type: () -> Dict[str, Any]
        # noinspection PyUnresolvedReferences
        params = super(WithDataSpecsAlsoForRequestParamsViewMixin, self).prepare_params()
        try:
            return self._clean_request_params(**params)
        except ParamValueCleaningError as cleaning_error:
            raise self.exc_on_param_value_cleaning_error(
                cleaning_error,
                invalid_params_set=frozenset(
                    name for name, _, _ in cleaning_error.error_info_seq))

    #
    # Extended `WithDataSpecsViewMixin`'s hooks

    # Note: the following method can be *extended* (with `super()`) in
    # subclasses -- but it should *not* be overridden completely.
    @classmethod
    def prepare_data_specs(cls):
        # type: () -> Dict[str, BaseDataSpec]
        return dict(
            super(WithDataSpecsAlsoForRequestParamsViewMixin, cls).prepare_data_specs(),

            # This is the data spec that will be used automatically to
            # clean request params -- you can override it in subclasses.
            request_params=cls.make_data_spec(),
        )

    #
    # Attributes/methods that can be overridden/extended in subclasses

    invalid_params_set_to_custom_exc_factory = {}   # type: Dict[FrozenSet[String], ExcFactory]

    def exc_on_param_value_cleaning_error(self, cleaning_error, invalid_params_set):
        # type: (ParamValueCleaningError, FrozenSet[String]) -> Exception
        custom_exc_factory = self.invalid_params_set_to_custom_exc_factory.get(invalid_params_set)
        if custom_exc_factory is not None:
            return custom_exc_factory()
        return cleaning_error  # (<- it will cause HTTP 400)

    #
    # Private implementation details

    # (provided automatically, see below)
    _clean_request_params = None   # type: Callable[..., Dict[str, Any]]

    @classmethod
    def _provide_clean_request_params_method(cls):
        assert hasattr(cls, 'data_specs') and isinstance(cls.data_specs, dict)
        assert 'request_params' in cls.data_specs

        @cleaning_kwargs_as_params_with_data_spec(cls.data_specs['request_params'])
        def _clean_request_params(*_, **cleaned_params):
            # type: (...) -> Dict[str, Any]
            return cleaned_params

        _clean_request_params.__module__ = cls.__module__
        _clean_request_params.__qualname__ = '{}.{}'.format(cls.__qualname__,
                                                            _clean_request_params.__name__)
        cls._clean_request_params = _clean_request_params
