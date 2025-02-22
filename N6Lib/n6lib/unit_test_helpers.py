# Copyright (c) 2013-2021 NASK. All rights reserved.

import contextlib
import copy
import functools
import json
import importlib
import inspect
import io
import re
import sys
import threading
import types
import unittest
import unittest.mock as mock
import zipfile

import pyramid.testing
from unittest.mock import (
    MagicMock,
    Mock,
    sentinel,
)
from sqlalchemy.orm.exc import NoResultFound
from webob.multidict import MultiDict

from n6lib.class_helpers import (
    ORDINARY_MAGIC_METHOD_NAMES,
    properly_negate_eq,
)
from n6lib.common_helpers import ascii_str
from n6sdk.tests._generic_helpers import TestCaseMixin as SDKTestCaseMixin



## TODO: doc, tests


#
# Packing/unpacking test helpers
#

def zip_data_in_memory(filename, data):
    buff_file = io.BytesIO()
    zip_archive = zipfile.ZipFile(buff_file, mode="w")
    zip_archive.writestr(filename, data)
    zip_archive.close()
    return buff_file.getvalue()


#
# Mocks for whom attribute access, mock calls
# and reset_mock() calls are thread-safe
#

_rlock_for_rlocked_mocks = threading.RLock()


class RLockedMock(Mock):

    def __getattr__(self, name):
        with _rlock_for_rlocked_mocks:
            return Mock.__getattr__(self, name)

    def __call__(*args, **kwargs):
        with _rlock_for_rlocked_mocks:
            return Mock.__call__(*args, **kwargs)

    def reset_mock(*args, **kwargs):
        with _rlock_for_rlocked_mocks:
            return Mock.reset_mock(*args, **kwargs)


class RLockedMagicMock(MagicMock):

    def __getattr__(self, name):
        with _rlock_for_rlocked_mocks:
            return MagicMock.__getattr__(self, name)

    def __call__(*args, **kwargs):
        with _rlock_for_rlocked_mocks:
            return MagicMock.__call__(*args, **kwargs)

    def reset_mock(*args, **kwargs):
        with _rlock_for_rlocked_mocks:
            return MagicMock.reset_mock(*args, **kwargs)


def __rlocked_patching_func(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if kwargs.get('new_callable') is None:
            kwargs['new_callable'] = RLockedMagicMock
        return func(*args, **kwargs)
    return wrapper

rlocked_patch = __rlocked_patching_func(mock.patch)
rlocked_patch.object = __rlocked_patching_func(mock.patch.object)
rlocked_patch.multiple = __rlocked_patching_func(mock.patch.multiple)



#
# Generic tests helpers
#

def _patching_method(method_name, patcher_maker, target_autocompletion=True):

    """
    This helper factory is not intended to be used directly.  It it
    used in the TestCaseMixin to create the following helper methods
    provided by TestCaseMixin: patch(), patch_object(), patch_dict(),
    patch_multiple().

    Each of the methods created with this helper factory does patching
    (using the specified `patcher_maker`, e.g., patch() from the `mock`
    package) and -- what is more interesting -- provides automatic
    cleanup: thanks to that you can just do in your test case methods:
    `self.patch(...)` (or `some_mock = self.patch(...)`) and that's all!
    (Neither `with` statements nor any manual cleanup are needed!)  The
    only requirement is that a test class in which you use this stuff is
    a subclass of unittest.TestCase (which provides the addCleanup()
    method, used by this stuff).

    A method created with this helper factory provides also another
    convenience feature: target auto-completion.  Instead of repeating
    again and again some long prefix, e.g. when doing in your tests:
    `self.patch('foo.bar.spam.ham.Something', ...)`, you can set: `<your
    TestCase class or instance>.default_patch_prefix = 'foo.bar.spam.ham'`
    -- and then in your test methods you can use the abbreviated form:
    `self.patch('Something', ...)`.

    See also: the comments in the source code of the TestCaseMixin class.

    ***

    Below: some doctests of the _patching_method() helper factory.

    >>> from unittest.mock import MagicMock, call, sentinel
    >>> m = MagicMock()
    >>> m.patch().start.return_value = sentinel.mock_thing
    >>> m.patch().stop = sentinel.stop
    >>> m.reset_mock()
    >>> class FakeTestCase(object):
    ...     addCleanup = m.addCleanup
    ...     default_patch_prefix = 'foo.bar'
    ...     do_patch = _patching_method('do_patch', m.patch)
    ...     do_patch_noc = _patching_method('do_patch_noc', m.patch,
    ...                                     target_autocompletion=False)
    >>> t = FakeTestCase()

    >>> t.do_patch('spam')
    sentinel.mock_thing
    >>> m.mock_calls == [
    ...     call.patch('foo.bar.spam'),
    ...     call.patch().start(),
    ...     call.addCleanup(sentinel.stop),
    ... ]
    True
    >>> m.reset_mock()

    >>> t.do_patch('ham.spam')
    sentinel.mock_thing
    >>> m.mock_calls == [
    ...     call.patch('ham.spam'),
    ...     call.patch().start(),
    ...     call.addCleanup(sentinel.stop),
    ... ]
    True
    >>> m.reset_mock()

    >>> t.do_patch('foo.bar.spam')
    sentinel.mock_thing
    >>> m.mock_calls == [
    ...     call.patch('foo.bar.spam'),
    ...     call.patch().start(),
    ...     call.addCleanup(sentinel.stop),
    ... ]
    True
    >>> m.reset_mock()

    >>> t.do_patch(sentinel.arg)
    sentinel.mock_thing
    >>> m.mock_calls == [
    ...     call.patch(sentinel.arg),
    ...     call.patch().start(),
    ...     call.addCleanup(sentinel.stop),
    ... ]
    True
    >>> m.reset_mock()

    >>> t.do_patch()
    Traceback (most recent call last):
      ...
    TypeError: do_patch() missing 1 required positional argument: 'target'

    >>> t.do_patch('spam', sentinel.arg, kwarg=sentinel.kwarg)
    sentinel.mock_thing
    >>> m.mock_calls == [
    ...     call.patch('foo.bar.spam', sentinel.arg, kwarg=sentinel.kwarg),
    ...     call.patch().start(),
    ...     call.addCleanup(sentinel.stop),
    ... ]
    True
    >>> m.reset_mock()

    >>> t.do_patch_noc('spam', sentinel.arg, kwarg=sentinel.kwarg)
    sentinel.mock_thing
    >>> m.mock_calls == [
    ...     call.patch('spam', sentinel.arg, kwarg=sentinel.kwarg),
    ...     call.patch().start(),
    ...     call.addCleanup(sentinel.stop),
    ... ]
    True
    >>> m.reset_mock()

    >>> t.do_patch('ham.spam', sentinel.arg, kwarg=sentinel.kwarg)
    sentinel.mock_thing
    >>> m.mock_calls == [
    ...     call.patch('ham.spam', sentinel.arg, kwarg=sentinel.kwarg),
    ...     call.patch().start(),
    ...     call.addCleanup(sentinel.stop),
    ... ]
    True
    >>> m.reset_mock()

    >>> t.do_patch_noc('ham.spam', sentinel.arg, kwarg=sentinel.kwarg)
    sentinel.mock_thing
    >>> m.mock_calls == [
    ...     call.patch('ham.spam', sentinel.arg, kwarg=sentinel.kwarg),
    ...     call.patch().start(),
    ...     call.addCleanup(sentinel.stop),
    ... ]
    True
    >>> m.reset_mock()

    >>> t.default_patch_prefix = 'foo.bar...'  # trailing dots are irrelevant
    >>> t.do_patch('spam', sentinel.arg, kwarg=sentinel.kwarg)
    sentinel.mock_thing
    >>> m.mock_calls == [
    ...     call.patch('foo.bar.spam', sentinel.arg, kwarg=sentinel.kwarg),
    ...     call.patch().start(),
    ...     call.addCleanup(sentinel.stop),
    ... ]
    True
    >>> m.reset_mock()

    >>> t.default_patch_prefix = None  # disable target auto-completion

    >>> t.do_patch('spam', sentinel.arg, kwarg=sentinel.kwarg)
    sentinel.mock_thing
    >>> m.mock_calls == [
    ...     call.patch('spam', sentinel.arg, kwarg=sentinel.kwarg),
    ...     call.patch().start(),
    ...     call.addCleanup(sentinel.stop),
    ... ]
    True
    >>> m.reset_mock()

    >>> t.do_patch('ham.spam', sentinel.arg, kwarg=sentinel.kwarg)
    sentinel.mock_thing
    >>> m.mock_calls == [
    ...     call.patch('ham.spam', sentinel.arg, kwarg=sentinel.kwarg),
    ...     call.patch().start(),
    ...     call.addCleanup(sentinel.stop),
    ... ]
    True
    >>> m.reset_mock()

    >>> t.do_patch_noc('spam', sentinel.arg, kwarg=sentinel.kwarg)
    sentinel.mock_thing
    >>> m.mock_calls == [
    ...     call.patch('spam', sentinel.arg, kwarg=sentinel.kwarg),
    ...     call.patch().start(),
    ...     call.addCleanup(sentinel.stop),
    ... ]
    True
    >>> m.reset_mock()

    >>> t.do_patch_noc('ham.spam', sentinel.arg, kwarg=sentinel.kwarg)
    sentinel.mock_thing
    >>> m.mock_calls == [
    ...     call.patch('ham.spam', sentinel.arg, kwarg=sentinel.kwarg),
    ...     call.patch().start(),
    ...     call.addCleanup(sentinel.stop),
    ... ]
    True
    >>> m.reset_mock()

    >>> del t.default_patch_prefix
    >>> FakeTestCase.default_patch_prefix = None  # also disable... (the same)
    >>> t.do_patch('spam', sentinel.arg, kwarg=sentinel.kwarg)
    sentinel.mock_thing
    >>> m.mock_calls == [
    ...     call.patch('spam', sentinel.arg, kwarg=sentinel.kwarg),
    ...     call.patch().start(),
    ...     call.addCleanup(sentinel.stop),
    ... ]
    True
    >>> m.reset_mock()
    """

    def _complete_target(self, target):
        if not isinstance(target, str) or '.' in target:
            return target
        # If the value of `target` is a `str` and does not contain '.'
        # we complete the value automatically by adding the prefix
        # defined as the `default_patch_prefix` attribute (if not None).
        prefix = getattr(self, 'default_patch_prefix', None)
        if prefix is None:
            return target
        return '{}.{}'.format(prefix.rstrip('.'), target)

    def _get_patching_method_arguments(self, target, /, *args, **kwargs):
        return self, target, args, kwargs

    _inner_name = _get_patching_method_arguments.__name__
    _get_patching_method_arguments.__qualname__ = 'TestCaseMixin.{}'.format(_inner_name)

    def a_patching_method(*raw_args, **raw_kwargs):
        try:
            (self,
             target,
             args,
             kwargs) = _get_patching_method_arguments(*raw_args, **raw_kwargs)  # noqa
        except TypeError as exc:
            # Let's make the error message contain the official name
            # of the method (Python 3.9 does not want to honour the
            # function's `__name__`/`__qualname__`; it seems it gets
            # the name from the internal code object...).
            adjusted_exc_message = ascii_str(exc).replace(_inner_name, method_name)
            raise TypeError(adjusted_exc_message) from None
        if target_autocompletion:
            target = _complete_target(self, target)
        patcher_args = (target,) + args
        patcher = patcher_maker(*patcher_args, **kwargs)
        mock_thing = patcher.start()
        self.addCleanup(patcher.stop)
        return mock_thing

    a_patching_method.__name__ = method_name
    a_patching_method.__qualname__ = 'TestCaseMixin.{}'.format(method_name)
    a_patching_method.__signature__ = inspect.signature(_get_patching_method_arguments)

    return a_patching_method


class TestCaseMixin(SDKTestCaseMixin):

    def assertJsonEqual(self, first, second, *args, **kwargs):
        if isinstance(first, (str, bytes, bytearray)):
            first = json.loads(first)
        if isinstance(second, (str, bytes, bytearray)):
            second = json.loads(second)
        self.assertEqual(first, second, *args, **kwargs)

    @contextlib.contextmanager
    def assertStateUnchanged(self, *args):
        state_before = copy.deepcopy(list(args))
        try:
            yield state_before
        finally:
            state_after = copy.deepcopy(list(args))
            self.assertEqual(state_after, state_before)

    #
    # patching convenience stuff

    # The following patching methods do not need any `with` statements
    # -- just call them at the beginning of your test method or in
    # setUp() (e.g.: `self.patch('some_module.SomeObject', ...)`).

    # [see also: the docstring of the _patching_method() function]

    patch = _patching_method(
        'patch',
        mock.patch)

    patch_object = _patching_method(
        'patch_object',
        mock.patch.object,
        target_autocompletion=False)

    patch_dict = _patching_method(
        'patch_dict',
        mock.patch.dict)

    patch_multiple = _patching_method(
        'patch_multiple',
        mock.patch.multiple)

    def patch_with_plug(self,
                        target,
                        exc_factory=NotImplementedError,
                        exc_msg_pattern=('use of {target} is unsupported when running '
                                         'tests from {self.__class__.__qualname__}'),
                        **patch_kwargs):
        exc_msg = exc_msg_pattern.format(
            self=self,
            target=target)
        plug = ExceptionRaisingPlug(exc_factory, exc_msg)
        self.patch(target, plug, **patch_kwargs)

    # The following attribute can be defined (in your test case class or
    # instance) to enable patch target auto-completion (i.e., adding the
    # defined prefix automatically to the given target if the target is
    # a `str` and does not contain the '.' character).
    # * Note #1: if a value of this attribute is a `str` which does not
    #   end with '.', the '.' character will be appended automatically.
    # * Note #2: *no* target auto-completion will be done if the value
    #   is None.
    default_patch_prefix = None


class ExceptionRaisingPlug(object):

    def __init__(self, exc_factory, *exc_args):
        self.__exc_factory = exc_factory
        self.__exc_args = exc_args

    # noinspection PyMethodParameters
    def __make_plug_meth(meth_name):
        def plug_method(self, /, *_, **__):
            exc = self.__exc_factory(*self.__exc_args)
            raise exc
        plug_method.__name__ = meth_name
        plug_method.__qualname__ = 'ExceptionRaisingPlug.{}'.format(meth_name)
        return plug_method

    for __meth_name in ORDINARY_MAGIC_METHOD_NAMES:
        # noinspection PyArgumentList
        locals()[__meth_name] = __make_plug_meth(__meth_name)

    del __make_plug_meth
    del __meth_name


class _ExpectedObjectPlaceholder(object):

    def __new__(cls, /, *args, **kwargs):
        self = super(_ExpectedObjectPlaceholder, cls).__new__(cls)
        self._constructor_args = args
        self._constructor_kwargs = kwargs
        return self

    def __eq__(self, other):
        if type(self) is type(other):
            return self.eq_test_for_same_type(other)
        else:
            return self.eq_test(other)

    __ne__ = properly_negate_eq  # (here explicit is better than implicit `:-)`)

    def __repr__(self):
        arg_reprs = [repr(a) for a in self._constructor_args]
        arg_reprs.extend(
            '{}={!r}'.format(k, v)
            for k, v in sorted(self._constructor_kwargs.items()))
        return '{}({})'.format(
            self.__class__.__qualname__,
            ', '.join(arg_reprs))

    # Overridable methods:

    # *must* be overridden
    def eq_test(self, other):
        raise NotImplementedError

    # *can* be overridden if needed
    def eq_test_for_same_type(self, other):
        return (self is other)


class AnyInstanceOf(_ExpectedObjectPlaceholder):

    """
    A class that implements a placeholder (somewhat similar to mock.ANY)
    that compares equal only to instances of the specified classes.

    >>> import numbers
    >>> any_str_or_integral = AnyInstanceOf(str, numbers.Integral)
    >>> any_str_or_integral
    AnyInstanceOf(<class 'str'>, <class 'numbers.Integral'>)

    >>> any_str_or_integral == 'foo'
    True
    >>> 'foo' == any_str_or_integral
    True
    >>> any_str_or_integral == 42
    True
    >>> 42 == any_str_or_integral
    True
    >>> any_str_or_integral == 12345678901234567890
    True
    >>> 12345678901234567890 == any_str_or_integral
    True

    >>> any_str_or_integral != 'foo'
    False
    >>> 'foo' != any_str_or_integral
    False
    >>> any_str_or_integral != 42
    False
    >>> 42 != any_str_or_integral
    False
    >>> any_str_or_integral != 12345678901234567890
    False
    >>> 12345678901234567890 != any_str_or_integral
    False

    >>> any_str_or_integral == b'foo'
    False
    >>> b'foo' == any_str_or_integral
    False
    >>> any_str_or_integral == 42.0
    False
    >>> 42.0 == any_str_or_integral
    False

    >>> any_str_or_integral != b'foo'
    True
    >>> b'foo' != any_str_or_integral
    True
    >>> any_str_or_integral != 42.0
    True
    >>> 42.0 != any_str_or_integral
    True

    >>> any_str_or_integral == any_str_or_integral
    True
    >>> any_str_or_integral == AnyInstanceOf(str, numbers.Integral)
    True
    >>> any_str_or_integral == AnyInstanceOf(numbers.Integral, str)
    True
    >>> any_str_or_integral == AnyInstanceOf(str, numbers.Integral, str)
    True
    >>> any_str_or_integral == AnyInstanceOf((str, numbers.Integral))
    True
    >>> any_str_or_integral == AnyInstanceOf((str,), numbers.Integral)
    True
    >>> any_str_or_integral == AnyInstanceOf(((str, numbers.Integral),), str)
    True
    >>> AnyInstanceOf(((str, numbers.Integral),), str) == any_str_or_integral
    True

    >>> any_str_or_integral != any_str_or_integral
    False
    >>> any_str_or_integral != AnyInstanceOf(str, numbers.Integral)
    False
    >>> any_str_or_integral != AnyInstanceOf(numbers.Integral, str)
    False
    >>> any_str_or_integral != AnyInstanceOf(str, numbers.Integral, str)
    False
    >>> any_str_or_integral != AnyInstanceOf((str, numbers.Integral))
    False
    >>> any_str_or_integral != AnyInstanceOf((str,), numbers.Integral)
    False
    >>> any_str_or_integral != AnyInstanceOf(((str, numbers.Integral),), str)
    False
    >>> AnyInstanceOf(((str, numbers.Integral),), str) != any_str_or_integral
    False

    >>> any_str_or_integral == AnyInstanceOf(str, bytearray, numbers.Integral)
    False
    >>> AnyInstanceOf(str, bytearray, numbers.Integral) == any_str_or_integral
    False
    >>> any_str_or_integral == AnyInstanceOf((str, bytearray), numbers.Integral)
    False
    >>> AnyInstanceOf((str, bytearray), numbers.Integral) == any_str_or_integral
    False
    >>> any_str_or_integral == AnyInstanceOf(((str,),), str)
    False
    >>> AnyInstanceOf(((str,),), str) == any_str_or_integral
    False
    >>> any_str_or_integral == AnyInstanceOf(((str, numbers.Integral),), str, int)
    False
    >>> AnyInstanceOf(((str, numbers.Integral),), str, int) == any_str_or_integral
    False

    >>> any_str_or_integral != AnyInstanceOf(str, bytearray, numbers.Integral)
    True
    >>> AnyInstanceOf(str, bytearray, numbers.Integral) != any_str_or_integral
    True
    >>> any_str_or_integral != AnyInstanceOf((str, bytearray), numbers.Integral)
    True
    >>> AnyInstanceOf((str, bytearray), numbers.Integral) != any_str_or_integral
    True
    >>> any_str_or_integral != AnyInstanceOf(((str,),), str)
    True
    >>> AnyInstanceOf(((str,),), str) != any_str_or_integral
    True
    >>> any_str_or_integral != AnyInstanceOf(((str, numbers.Integral),), str, int)
    True
    >>> AnyInstanceOf(((str, numbers.Integral),), str, int) != any_str_or_integral
    True
    """

    def __init__(self, *classes):
        self._classes = self.__get_sorted_unique_flattened_classes(classes)

    def __get_sorted_unique_flattened_classes(self, classes):
        unique_flattened = self.__iter_unique_classes(self.__iter_flattened_classes(classes))
        return tuple(sorted(unique_flattened, key=id))

    def __iter_unique_classes(self, classes):
        seen = []
        for cls in classes:
            if any((cls is c) for c in seen):
                continue
            seen.append(cls)
            yield cls

    def __iter_flattened_classes(self, classes):
        for cls in classes:
            if isinstance(cls, tuple):
                for c in self.__iter_flattened_classes(cls):
                    yield c
            else:
                yield cls

    def eq_test(self, other):
        return isinstance(other, self._classes)

    def eq_test_for_same_type(self, other):
        return self._classes == other._classes


class AnyFunctionNamed(_ExpectedObjectPlaceholder):

    """
    A class that implements a placeholder (somewhat similar to mock.ANY)
    that compares equal only to functions whose name is equal to the
    specified one.

    >>> any_func_named_foo = AnyFunctionNamed('foo')
    >>> any_func_named_foo
    AnyFunctionNamed('foo')
    >>> AnyFunctionNamed(name='foo')  # the same, only repr slightly different
    AnyFunctionNamed(name='foo')

    >>> def foo(): pass
    >>> any_func_named_foo == foo
    True
    >>> foo == any_func_named_foo
    True
    >>> any_func_named_foo != foo
    False
    >>> foo != any_func_named_foo
    False

    >>> def bar(): pass
    >>> any_func_named_foo == bar
    False
    >>> bar == any_func_named_foo
    False
    >>> any_func_named_foo != bar
    True
    >>> bar != any_func_named_foo
    True

    >>> any_func_named_foo == any_func_named_foo
    True
    >>> any_func_named_foo == AnyFunctionNamed(name='foo')
    True
    >>> any_func_named_foo != any_func_named_foo
    False
    >>> any_func_named_foo != AnyFunctionNamed(name='foo')
    False

    >>> any_func_named_foo == AnyFunctionNamed('bar')
    False
    >>> AnyFunctionNamed(name='bar') == any_func_named_foo
    False
    >>> any_func_named_foo != AnyFunctionNamed('bar')
    True
    >>> AnyFunctionNamed(name='bar') != any_func_named_foo
    True
    """

    def __init__(self, name):
        self._name = name

    def eq_test(self, other):
        return (
            isinstance(other, types.FunctionType) and
            self._name == other.__name__)

    def eq_test_for_same_type(self, other):
        return self._name == other._name


class AnyDictIncluding(_ExpectedObjectPlaceholder):

    """
    A class that implements a placeholder (somewhat similar to mock.ANY)
    that compares equal only to `dict` instances that contain *at least*
    (among others) all specified items.

    >>> any_dict_including_foobar = AnyDictIncluding(foo='bar')
    >>> any_dict_including_foobar
    AnyDictIncluding(foo='bar')

    >>> d1 = {'foo': 'bar', 'spam': 'ham'}
    >>> any_dict_including_foobar == d1
    True
    >>> d1 == any_dict_including_foobar
    True
    >>> any_dict_including_foobar != d1
    False
    >>> d1 != any_dict_including_foobar
    False

    >>> d2 = {'bar': 'foo', 'spam': 'ham'}
    >>> any_dict_including_foobar == d2
    False
    >>> d2 == any_dict_including_foobar
    False
    >>> any_dict_including_foobar != d2
    True
    >>> d2 != any_dict_including_foobar
    True

    >>> d3 = {'goooo': 'bar', 'spam': 'ham'}
    >>> any_dict_including_foobar == d3
    False
    >>> d3 == any_dict_including_foobar
    False
    >>> any_dict_including_foobar != d3
    True
    >>> d3 != any_dict_including_foobar
    True

    >>> d4 = {'foo': 'gar', 'spam': 'ham'}
    >>> any_dict_including_foobar == d4
    False
    >>> d4 == any_dict_including_foobar
    False
    >>> any_dict_including_foobar != d4
    True
    >>> d4 != any_dict_including_foobar
    True

    >>> li = list(d1.items())
    >>> any_dict_including_foobar == li
    False
    >>> li == any_dict_including_foobar
    False
    >>> any_dict_including_foobar != li
    True
    >>> li != any_dict_including_foobar
    True

    >>> any_dict_including_foobar == any_dict_including_foobar
    True
    >>> any_dict_including_foobar == AnyDictIncluding(foo=u'bar')
    True
    >>> any_dict_including_foobar != any_dict_including_foobar
    False
    >>> any_dict_including_foobar != AnyDictIncluding(foo=u'bar')
    False

    >>> any_dict_including_foobar == AnyDictIncluding(foo=u'barrrrr')
    False
    >>> AnyDictIncluding(foo=u'barrrrr') == any_dict_including_foobar
    False
    >>> any_dict_including_foobar != AnyDictIncluding(foo=u'barrrrr')
    True
    >>> AnyDictIncluding(foo=u'barrrrr') != any_dict_including_foobar
    True
    """

    def __init__(self, /, **required_items):
        self._required_items = required_items

    def eq_test(self, other):
        return (
            isinstance(other, dict) and
            all(key in other and value == other[key]
                for key, value in self._required_items.items()))

    def eq_test_for_same_type(self, other):
        return self._required_items == other._required_items


# TODO: docs, tests
class AnyObjectWhoseVarsInclude(AnyDictIncluding):

    def eq_test(self, other):
        return AnyDictIncluding.eq_test(self, vars(other))


# TODO: docs, tests
class AnyInstanceOfWhoseVarsInclude(AnyInstanceOf, AnyObjectWhoseVarsInclude):

    def __init__(self, /, *classes, **required_items):
        AnyInstanceOf.__init__(self, *classes)
        AnyObjectWhoseVarsInclude.__init__(self, **required_items)

    def eq_test(self, other):
        return (AnyInstanceOf.eq_test(self, other) and
                AnyObjectWhoseVarsInclude.eq_test(self, other))

    def eq_test_for_same_type(self, other):
        return (AnyInstanceOf.eq_test_for_same_type(self, other) and
                AnyObjectWhoseVarsInclude.eq_test_for_same_type(self, other))


# TODO: docs, tests
class AnyMatchingRegex(_ExpectedObjectPlaceholder):

    def __init__(self, regex):
        if isinstance(regex, (str, bytes)):
            regex = re.compile(regex)
        self._regex = regex

    def eq_test(self, other):
        return self._regex.search(other)


class JSONWhoseContentIsEqualTo(_ExpectedObjectPlaceholder):

    """
    A class that implements a placeholder (somewhat similar to mock.ANY)
    that compares equal only to `str`/`bytes`/`bytearray` instances that,
    when `json.loads()` is applied to them, produce an object equal to
    the specified object.

    >>> json1 = JSONWhoseContentIsEqualTo({'key': 42})
    >>> json1
    JSONWhoseContentIsEqualTo({'key': 42})
    >>> JSONWhoseContentIsEqualTo(data={'key': 42})  # the same, only repr slightly different
    JSONWhoseContentIsEqualTo(data={'key': 42})

    >>> json1 == b'{"key": 42}'
    True

    >>> json1 == u'{"key": 42}'
    True
    >>> b'{"key": 42}' == json1
    True
    >>> u'{"key": 42}' == json1
    True
    >>> json1 != b'{"key": 42}'
    False
    >>> json1 != u'{"key": 42}'
    False
    >>> b'{"key": 42}' != json1
    False
    >>> u'{"key": 42}' != json1
    False

    >>> json2 = JSONWhoseContentIsEqualTo([42, 'spam', {'key': 42}])
    >>> json2 == b'[42, "spam", {"key": 42}]'
    True
    >>> json2 == u'[42, "spam", {"key": 42}]'
    True
    >>> b'[42, "spam", {"key": 42}]' == json2
    True
    >>> u'[42, "spam", {"key": 42}]' == json2
    True
    >>> json2 != b'[42, "spam", {"key": 42}]'
    False
    >>> json2 != u'[42, "spam", {"key": 42}]'
    False
    >>> b'[42, "spam", {"key": 42}]' != json2
    False
    >>> u'[42, "spam", {"key": 42}]' != json2
    False

    >>> json1 == b'{"another-key": 42}'
    False
    >>> json1 == u'{"key": 444442}'
    False
    >>> json1 == b'[{"key": 42}]'
    False
    >>> json1 == u'"key"'
    False
    >>> json1 == b'foo'
    False
    >>> json1 == {"key": 42}
    False
    >>> json1 == 42
    False
    >>> json1 == json2
    False
    >>> b'{"another-key": 42}' == json1
    False
    >>> u'{"key": 444442}' == json1
    False
    >>> b'[{"key": 42}]' == json1
    False
    >>> u'"key"' == json1
    False
    >>> b'foo' == json1
    False
    >>> {"key": 42} == json1
    False
    >>> 42 == json1
    False
    >>> json2 == json1
    False

    >>> json1 != b'{"another-key": 42}'
    True
    >>> json1 != u'{"key": 444442}'
    True
    >>> json1 != b'[{"key": 42}]'
    True
    >>> json1 != u'"key"'
    True
    >>> json1 != b'foo'
    True
    >>> json1 != {"key": 42}
    True
    >>> json1 != 42
    True
    >>> b'{"another-key": 42}' != json1
    True
    >>> u'{"key": 444442}' != json1
    True
    >>> b'[{"key": 42}]' != json1
    True
    >>> u'"key"' != json1
    True
    >>> b'foo' != json1
    True
    >>> {"key": 42} != json1
    True
    >>> 42 != json1
    True

    >>> json1 == json1
    True
    >>> json1 == JSONWhoseContentIsEqualTo(data={u'key': 42})
    True
    >>> JSONWhoseContentIsEqualTo(data={u'key': 42}) == json1
    True
    >>> json1 != json1
    False
    >>> json1 != JSONWhoseContentIsEqualTo(data={u'key': 42})
    False
    >>> JSONWhoseContentIsEqualTo(data={u'key': 42}) != json1
    False

    >>> json1 == JSONWhoseContentIsEqualTo(data={u'key': 444442})
    False
    >>> JSONWhoseContentIsEqualTo(data={u'key': 444442}) == json1
    False
    >>> json1 != JSONWhoseContentIsEqualTo(data={u'key': 444442})
    True
    >>> JSONWhoseContentIsEqualTo(data={u'key': 444442}) != json1
    True

    >>> json1 == json2
    False
    >>> json2 == json1
    False
    >>> json1 != json2
    True
    >>> json2 != json1
    True

    >>> json1 == bytearray(b'{"key": 42}')
    True
    >>> bytearray(b'{"key": 42}') == json1
    True
    >>> json1 != bytearray(b'{"key": 42}')
    False
    >>> bytearray(b'{"key": 42}') != json1
    False
    >>> json1 == bytearray(b'{"another-key": 42}')
    False
    >>> bytearray(b'{"key": 42123}') == json1
    False
    >>> json1 != bytearray(b'{"key": 42123}')
    True
    >>> bytearray(b'{"another-key": 42}') != json1
    True
    """

    def __init__(self, data):
        self._data = data

    def eq_test(self, other):
        if not isinstance(other, (str, bytes, bytearray)):
            return False
        try:
            other_data = json.loads(other)
        except ValueError:
            return False
        return self._data == other_data

    def eq_test_for_same_type(self, other):
        return self._data == other._data


# TODO: document it or deprecate it?
class MethodProxy(object):

    def __init__(self, cls, first_arg_mock, class_attrs=()):
        self.__cls = cls
        self.__first_arg_mock = first_arg_mock
        if isinstance(class_attrs, str):
            class_attrs = class_attrs.replace(',', ' ').split()
        for name in class_attrs:
            # maybe TODO: make it more smart, taking into account
            #             various (modern-Python-specific) cases...
            obj = getattr(cls, name)
            if inspect.ismethod(obj) or self.__is_function_implementing_method(cls, name, obj):
                assert isinstance(obj, (types.MethodType, types.FunctionType))
                obj = getattr(self, name)
            else:
                assert not isinstance(obj, types.MethodType)
            setattr(first_arg_mock, name, obj)

    def __getattribute__(self, name):
        if name.startswith('_MethodProxy__'):
            return super(MethodProxy, self).__getattribute__(name)
        cls = self.__cls
        obj = getattr(cls, name)
        if inspect.ismethod(obj):
            assert isinstance(obj, types.MethodType)
            return functools.partial(obj.__func__, self.__first_arg_mock)
        elif self.__is_function_implementing_method(cls, name, obj):
            assert isinstance(obj, types.FunctionType)
            return functools.partial(obj, self.__first_arg_mock)
        else:
            assert not isinstance(obj, types.MethodType)
            raise TypeError(
                '{!a} ({!a}.{}) is not a method'.format(
                    obj, cls, name))

    def __is_function_implementing_method(self, cls, name, obj):
        # In Py3 (unlike in Py2), if a user-defined function is an
        # attribute of a class and we try to get that function from
        # that class (not from its instance), we get just that function
        # (i.e., there are no *unbound methods*).
        return (inspect.isfunction(obj) and
                obj is inspect.getattr_static(cls, name, None))  # *not* a staticmethod or what...



#
# Test helpers related to SQLAlchemy and/or `n6lib.auth_db`
#

class DBSessionMock(mock.MagicMock):

    def add(self, inst):
        table = inst.__tablename__
        self.session_state.setdefault(table, [])
        self.session_state[table].append(inst)
        self.collection.setdefault(table, [])
        self.collection[table].append(inst)


class QueryMock(mock.MagicMock):

    def filter(self, condition):
        col = condition.left.key
        val = condition.right.value
        m = mock.Mock()
        m.one.return_value = self._get_from_db(self.table, col, val)
        return m

    def all(self):
        return self.collection.get(self.table, [])

    def _get_from_db(self, table, col, val):
        for obj in self.collection.get(table, []):
            if getattr(obj, col) == val:
                return obj
        raise NoResultFound


class DBConnectionPatchMixin(TestCaseMixin):

    """
    A class mixin providing basic interface for patching database connectors.
    """

    def make_patches(self, collection, session_state):
        """
        Create basic patches.
        """
        self.collection = collection
        self.session_state = session_state
        self.session_mock = self.get_session_mock(self.collection, self.session_state)
        self.patch_db_connector(self.session_mock)

    @staticmethod
    def get_session_mock(collection, session_state):
        """
        Get a mock essential for patching of the database interface.

        The mock will be used as a return value of the database
        connector, which may be a session or a "context" object
        (containing a session object), depending on where it is used.

        It is named the 'context mock' for simplicity.

        Args:
            `collection`:
                A mapping, which then will be used as a patched
                database collection.
            `session_state`:
                A mapping, which then will be used as a container
                for objects temporarily held in a patched session
                object's storage (objects normally added by
                the `add()` method of a session object).
                It should be an empty dict for a new session.

        Returns:
            a MagicMock() class instance, which is adjusted to serve
            as a mock of the return value of database connector
            context manager, or as an attribute of returned
            "context" object in some cases.
        """
        def query_effect(model_cls):
            return QueryMock(table=model_cls.__tablename__, collection=collection)
        m = DBSessionMock(session_state=session_state, collection=collection)
        m.query.side_effect = query_effect
        return m

    def patch_db_connector(self, session_mock):
        """
        Patch the database connector instance.

        Args:
            `session_mock`:
                The object got earlier from the `get_session_mock()`
                method. It should be provided by the patched database
                connector upon calling its `__enter__()` method (when
                the patched connector is used as a context manager).

        This method should patch the database connector being used so
        that no errors will occur. Connectors are mostly used as
        context managers and so the `session_mock` argument
        holds the object that should be returned upon entering
        with the provided database connector mock, or it should
        be used as an attribute of a returned "context" object
        in other cases.

        This method is considered abstract and should be overridden
        in deriving classes. It is so as some classes need specific
        instance of the connector to be patched while other will
        need whole class patched. Typically, patching should be done
        with the `patch()` method (or `patch_object()` etc.; see: the
        `TestCaseMixin` class which is a superclass of this mixin).

        Example implementation:

        ```python
        def patch_db_connector(self, session_mock):
            self.connector_mock = self.patch('n6lib.my_module.SQLAuthDBConnector')
            self.connector_mock.return_value.__enter__.return_value = session_mock
        ```
        """
        raise NotImplementedError



#
# Test helpers related to Pyramid and/or `{n6sdk,n6lib}.pyramid_commons`
#

class RequestHelperMixin(object):

    def prepare_pyramid_unittesting(self):
        """
        Set up the `pyramid.testing` stuff and register a cleanup callback.

        Returns:
            A `pyramid.config.Configurator` instance.
        """
        assert isinstance(self, unittest.TestCase)
        pyramid_configurator = pyramid.testing.setUp()
        self.addCleanup(pyramid.testing.tearDown)
        return pyramid_configurator

    @classmethod
    def create_request(cls, view_class, **kwargs):
        """
        Make a Pyramid request object, associated with a view (being an
        instance of a subclass of the root base class of *n6* views --
        `AbstractViewBase`) and equipped with an additional method,
        `perform()`, which easies writing unit tests of that view.

        For an example use, see the `perform_request()` method
        of the '_N6BrokerViewTestingMixin` class defined in the
        `n6brokerauthapi.tests.test_views_with_auth_stream_api`
        module.

        Args (positional-only):
            `view_class`:
                An abstract subclass of `AbstractViewBase` (note that
                a concrete subclass of it will be obtained by this
                mixin's machinery by calling the `concrete_view_class()`
                method of `view_class` -- see below...).

        Arbitrary kwargs (keyword-only):
            To be transformed into request's `params`. Their values
            should be `str`, or lists of `str` (the latter in the case
            of a request parameter that has multiple values).

        Returns:
            A `pyramid.request.Request` instance.

        **Important:** the returned request instance contains an
        additional (non-standard, added by `RequestHelperMixin`)
        argumentless method: `perform()` -- intended to be called in
        your test cases.

        A context of the following stuff is bound to that method:

        * the request instance;

        * the `view_class` class;

        * the concrete test case class (being a subclass of
          `RequestHelperMixin`) -- below referred to as *test class*.

        The `perform()` method acts in the following way:

        * First it calls the `get_concrete_view_class_kwargs()` class
          method of the *test class* (`RequestHelperMixin` provides a
          default implementation of that method -- see its docstring),
          with `view class` and the request instance as the arguments.

        * The return value of that call is a dict of keyword arguments
          which, then, are passed into the `concrete_view_class()`
          class method of `view_class`. (Normally, this step is done as
          a part of the activity of `{n6sdk,n6lib}.pyramid_commons`'s
          config helpers -- but, for the purposes of our tests, it is a
          responsibility of `perform()`.)

        * A concrete view class being the return value of that call
          (see the implementations of `concrete_view_class()` provided
          by `AbstractViewBase` and its subclasses...) is then
          instantiated with two positional arguments -- `context` and
          `request`:

          * the `context` argument is produced by calling the
            `get_view_context()` method of the *test class*
            (`RequestHelperMixin` provides a default implementation of
            that method -- see its docstring), with the concrete view
            class and the request instance as the arguments;

          * the `request` argument is just our request instance.

        * Then, the resultant view instance is called (without
          arguments).

        * The return value of that call is a response object (instance
          of `pyramid.response.Response`). It becomes the `perform()`'s
          return value.
        """
        request = pyramid.testing.DummyRequest()
        request.params = cls.__make_request_params(kwargs)
        request.perform = cls.__make_request_perform_method(view_class, request)
        return request

    @staticmethod
    def __make_request_params(kwargs):
        params = MultiDict()
        for key, val in kwargs.items():
            assert isinstance(key, str)
            if isinstance(val, str):
                params[key] = val
            else:
                assert isinstance(val, (list, tuple))
                for v in val:
                    assert isinstance(v, str)
                    params.add(key, v)
        return params

    @classmethod
    def __make_request_perform_method(cls, view_class, request):
        def perform():
            """
            Create a view instance associated with this request, and
            call that instance immediately (forwarding the return value
            which is supposed to be a response object).
            """
            view_instance = cls.make_view_instance(view_class, request)
            response = view_instance()
            return response
        return perform

    @classmethod
    def make_view_instance(cls, view_class, request):
        """
        Create an instance of the given view class, associated with the given request.
        (This method is invoked by `request.perform()` -- see the docs of `create_request()`.)
        """
        concrete_view_class_kwargs = cls.get_concrete_view_class_kwargs(view_class, request)
        concrete_view_class = view_class.concrete_view_class(**concrete_view_class_kwargs)
        view_context = cls.get_view_context(concrete_view_class, request)
        view_instance = concrete_view_class(view_context, request)
        return view_instance

    @classmethod
    def get_concrete_view_class_kwargs(cls, view_class, request):
        """
        Get a dict of keyword arguments for the `concrete_view_class()`
        method of `view_class`.

        Note that in your test classes you may need to override/extend
        `get_concrete_view_class_kwargs()` -- because it depends on a
        particular `view_class` what keyword arguments are expected by
        `concrete_view_class()`.
        """
        return dict(resource_id='mock_resource_id', pyramid_configurator=sentinel.configurator)

    @classmethod
    def get_view_context(cls, concrete_view_class, request):
        """
        Get the `context` argument for the view instance constructor.

        Because that argument is typically ignored in *n6* views
        (see `AbstractViewBase` and its subclasses...) the default
        implementation of `get_view_context()` returns just
        `mock.sentinel.context`.
        """
        return sentinel.context


#
# Deprecated test helpers (to be removed)
#

### XXX: this function seems to be needless --
###      just use mock.patch(..., create=True) instead
@contextlib.contextmanager
def patch_always(dotted_name, *patch_args, **patch_kwargs):
    # patch also when the target object does not exist
    module_name, attr_name = dotted_name.rsplit('.', 1)
    module_obj = importlib.import_module(module_name)
    _placeholder = object()
    try:
        getattr(module_obj, attr_name)
    except AttributeError:
        setattr(module_obj, attr_name, _placeholder)
    try:
        with mock.patch.object(
                module_obj, attr_name,
                *patch_args, **patch_kwargs) as resultant_mock:
            yield resultant_mock
    finally:
        if getattr(module_obj, attr_name) is _placeholder:
            delattr(module_obj, attr_name)



#
# Test running helpers
#

def run_module_doctests(m=None, *args, **kwargs):
    """
    Like doctest.testmod(...) but on success always prints an info message.
    """
    import doctest
    failures, tests = doctest.testmod(m, *args, **kwargs)
    if not failures:
        module_repr = (repr(m) if m is not None
                       else repr(sys.modules['__main__']))
        sys.stdout.write('{0} doctests ran successfully for module {1}\n'
                         .format(tests, module_repr))
        sys.stdout.flush()
    return failures, tests


if __name__ == '__main__':
    run_module_doctests()
