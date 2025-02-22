# -*- coding: utf-8 -*-

# Copyright (c) 2013-2021 NASK. All rights reserved.


import collections as collections_abc  #3: import collections.abc as collections_abc

from n6sdk.encoding_helpers import ascii_str, as_unicode


#
# Generic mix-ins
#

class _ErrorWithPublicMessageMixin(object):

    r"""
    A mix-in class that provides the :attr:`public_message` property.

    The value of this property is a :class:`str`.  It is taken either
    from the `public_message` constructor keyword argument (which should
    be a :class:`str`) or -- if the argument was not specified -- from
    the value of the :attr:`default_public_message` attribute (which
    should also be a :class:`str`).

    The public message should be a complete sentence (or several
    sentences): first word capitalized (if not being an identifier
    that begins with a lower case letter) + the period at the end.

    .. warning::

       Generally, the message is intended to be presented to clients.
       **Ensure that you do not disclose any sensitive details in the
       message.**

    .. seealso::

       See the documentation of the public exception classes provided by
       this module.

    The :class:`str`conversion implemented by the class uses the value
    of :attr:`public_message`:

    >>> class SomeError(_ErrorWithPublicMessageMixin, Exception):
    ...     pass
    ...
    >>> str(SomeError('a', 'b'))  # using attribute default_public_message
    'Internal error.'
    >>> str(SomeError('a', 'b', public_message='Sp\xc4\x85m.'))                  #3--
    'Sp\xc4\x85m.'
    >>> str(SomeError('a', 'b', public_message=u'Sp\u0105m.'))                   #3: `u`--
    'Sp\xc4\x85m.'
    >>> unicode(SomeError('a', 'b'))  # using attribute default_public_message   #3--
    u'Internal error.'
    >>> unicode(SomeError('a', 'b', public_message='Sp\xc4\x85m.'))              #3--
    u'Sp\u0105m.'
    >>> unicode(SomeError('a', 'b', public_message=u'Sp\u0105m.'))               #3--
    u'Sp\u0105m.'

    The :func:`repr` conversion results in a programmer-readable
    representation (containing the class name, :func:`repr`-formatted
    constructor arguments and the :attr:`public_message` property):

    >>> SomeError('a', 'b')   # using class's default_public_message
    <SomeError: args=('a', 'b'); public_message=u'Internal error.'>
    >>> SomeError('a', 'b', public_message='Spam.')
    <SomeError: args=('a', 'b'); public_message=u'Spam.'>
    """

    #: (overridable in subclasses)
    default_public_message = u'Internal error.'

    def __init__(self, *args, **kwargs):
        try:
            public_message = kwargs.pop('public_message')                        #3: better keyword-only arg `public_message`...
        except KeyError:
            pass
        else:
            self._public_message = as_unicode(public_message)
        super(_ErrorWithPublicMessageMixin, self).__init__(*args, **kwargs)

    @property
    def public_message(self):
        """The aforementioned property."""
        try:
            return self._public_message
        except AttributeError:
            # (in subclasses `default_public_message` can also be a @property)
            self._public_message = as_unicode(self.default_public_message)
            return self._public_message

    def __str__(self):
        return self.public_message.encode('utf-8')                               #3: `.encode('utf-8')`--

    def __unicode__(self):                                                       #3--
        return self.public_message                                               #3--
                                                                                 #3--
    def __repr__(self):
        return ('<{0.__class__.__name__}: args={0.args!r}; '                     #3: `__name__`->`__qualname__`
                'public_message={0.public_message!r}>'.format(self))


class _KeyCleaningErrorMixin(object):
    """
    Mix-in for *key cleaning*-related exception classes.

    Each instance of such a class:

    * should be initialized with two (positional or keyword) arguments:
      `illegal_keys` and `missing_keys` that should be sets of --
      respectively -- illegal or missing keys (each key being a
      :class:`str`);

    * exposes these arguments as the :attr:`illegal_keys` and
      :attr:`missing_keys` attributes (for possible later inspection).
    """

    def __init__(self, illegal_keys, missing_keys):
        self.illegal_keys = illegal_keys
        self.missing_keys = missing_keys
        super(_KeyCleaningErrorMixin, self).__init__(illegal_keys, missing_keys)


class _ValueCleaningErrorMixin(object):
    """
    Mix-in for *value cleaning*-related exception classes.

    Each instance of such a class:

    * should be initialized with one argument being a list of (*<key>*,
      *<offending value or list of offending values>*, *<actual exception>*)
      tuples -- where *<actual exception>* is the exception instance
      that caused the error (e.g., a :exc:`~exceptions.ValueError` or an
      instance of some :exc:`_ErrorWithPublicMessageMixin` subclass);

    * exposes that argument as the :attr:`error_info_seq` attribute
      (for possible later inspection).
    """

    def __init__(self, error_info_seq):
        self.error_info_seq = error_info_seq
        super(_ValueCleaningErrorMixin, self).__init__(error_info_seq)


#
# Actual exception classes
#

class FieldValueError(_ErrorWithPublicMessageMixin, ValueError):

    """
    Intended to be raised in :meth:`~.Field.clean_param_value` and
    :meth:`~.Field.clean_result_value` methods of
    :class:`n6sdk.data_spec.fields.Field` subclasses.

    When using it in a :meth:`~.Field.clean_param_value`'s
    implementation it is recommended (though not required) to
    instantiate the exception specifying the `public_message`
    keyword argument.

    Typically, this exception (as any other :exc:`~exceptions.Exception`
    subclass/instance raised in a field's :meth:`clean_*_value` method)
    is caught by the *n6sdk* machinery -- then, appropriately,
    :exc:`ParamValueCleaningError` (with :attr:`public_message`
    including :attr:`public_message` of this exception -- see: the
    :exc:`ParamValueCleaningError` documentation) or
    :exc:`ResultValueCleaningError` (with :attr:`public message` being
    just the default and safe ``"Internal error."``) is raised.

    .. seealso::

       See: :exc:`_ErrorWithPublicMessageMixin` as well as the
       :exc:`ParamValueCleaningError` and
       :exc:`ResultValueCleaningError`.
    """


class FieldValueTooLongError(FieldValueError):

    """
    Intended to be raised when the length of the given value is too big.

    Instances *must* be initialized with the following keyword-only
    arguments:

    * `field` (:class:`n6sdk.data_spec.fields.Field` instance):
      the field whose method raised the exception;
    * `checked_value`:
      the value which caused the exception (possibly already partially
      processed by methods of `field`);
    * `max_length`:
      the length limit that was exceeded (what caused the exception).

    They become attributes of the exception instance -- respectively:
    :attr:`field`, :attr:`checked_value`, :attr:`max_length`.

    >>> exc = FieldValueTooLongError(
    ...     field='sth', checked_value=['foo'], max_length=42)
    >>> exc.field
    'sth'
    >>> exc.checked_value
    ['foo']
    >>> exc.max_length
    42

    >>> FieldValueTooLongError(   # doctest: +ELLIPSIS
    ...     checked_value=['foo'], max_length=42)
    Traceback (most recent call last):
      ...
    TypeError: __init__() needs keyword-only argument field

    >>> FieldValueTooLongError(   # doctest: +ELLIPSIS
    ...     field='sth', max_length=42)
    Traceback (most recent call last):
      ...
    TypeError: __init__() needs keyword-only argument checked_value

    >>> FieldValueTooLongError(   # doctest: +ELLIPSIS
    ...     field='sth', checked_value=['foo'])
    Traceback (most recent call last):
      ...
    TypeError: __init__() needs keyword-only argument max_length
    """

    def __init__(self, *args, **kwargs):
        try:
            self.field = kwargs.pop('field')
            self.checked_value = kwargs.pop('checked_value')
            self.max_length = kwargs.pop('max_length')
        except KeyError as exc:
            [kw] = exc.args
            raise TypeError('__init__() needs keyword-only argument ' + kw)      #3: better use real keyword-only args...
        super(FieldValueTooLongError, self).__init__(*args, **kwargs)


class DataAPIError(_ErrorWithPublicMessageMixin, Exception):

    """
    The base class for exceptions raised by *views* or APIs they invoke
    (in particular, the *data specification* machinery or the *data
    backend API*) -- "HTTP-4xx-like" or "HTTP-500-like" ones (see the
    subclasses...).

    (They are **not** intended to be raised in :meth:`clean_*_value` of
    :class:`~n6sdk.data_spec.fields.Field` subclasses -- use
    :exc:`FieldValueError` instead.)

    Note: legacy code may instantiate (and raise) :exc:`DataAPIError`
    **directly** (to indicate some "HTTP-500-like" error), but this
    should be avoided in a new code.

    >>> exc = DataAPIError('a', 'b')
    >>> exc.args
    ('a', 'b')
    >>> exc.public_message   # using attribute default_public_message            #3: `u`--
    u'Internal error.'
    >>> unicode(exc)                                                             #3--
    u'Internal error.'
    >>> str(exc)
    'Internal error.'
    >>> u'{}'.format(exc)                                                        #3--
    u'Internal error.'
    >>> '{}'.format(exc)
    'Internal error.'

    >>> exc = DataAPIError('a', 'b', public_message='Spam.')
    >>> exc.args
    ('a', 'b')
    >>> exc.public_message   # the message passed into the constructor           #3: `u`--
    u'Spam.'
    >>> unicode(exc)                                                             #3--
    u'Spam.'
    >>> str(exc)
    'Spam.'
    >>> u'{}'.format(exc)                                                        #3--
    u'Spam.'
    >>> '{}'.format(exc)
    'Spam.'
    """


class DataLookupError(DataAPIError):
    """
    The base class for *stuff-the-client-refers-to-not-found*
    ("HTTP-404-like") exceptions -- raised by *views* or APIs they
    invoke.
    """
    default_public_message = u'Could not find what was referred to.'


class AuthorizationError(DataAPIError):
    """
    The base class for *rejecting-the-client-request* ("HTTP-403-like")
    exceptions -- raised by *views* or APIs they invoke.

    This class can also be instantiated (and raised) directly (in
    particular, to indicate that access to a certain data/resource is
    *not* granted for the entity represented by the client).
    """
    default_public_message = u'Authorization denied.'


class DataFromClientError(DataAPIError):
    """
    The base class for *incorrect-data-from-the-client* ("HTTP-400-like")
    exceptions -- raised by *views* or APIs they invoke (in particular
    the *data specification* machinery).
    """
    default_public_message = u'Incorrect client-provided data.'


class ParamCleaningError(DataFromClientError):
    """
    The base class for exceptions (to be treated as "HTTP-400-like"
    ones) raised when query parameter cleaning (or some validation
    before the actual cleaning) fails.

    Instances of its subclasses are raised by the *data specification*
    machinery.

    This class can also be instantiated directly (and raised) by
    *views*.
    """
    default_public_message = u'Invalid parameter(s).'


class ParamKeyCleaningError(_KeyCleaningErrorMixin, ParamCleaningError):
    r"""
    This exception should be raised by the *data specification*
    machinery (in particular, it is raised in
    :meth:`n6sdk.data_spec.BaseDataSpec.clean_param_dict`) when some
    client-specified parameter keys (names) are illegal and/or missing.

    This exception class provides :attr:`default_public_message` (see:
    :exc:`_ErrorWithPublicMessageMixin`) as a property whose value is a
    nice, user-readable message that includes all illegal and missing
    keys.

    >>> try:
    ...     raise ParamKeyCleaningError({'zz', 'x'}, {'Ę', 'b'})
    ... except ParamCleaningError as e:
    ...     exc = e
    ...
    >>> exc.public_message == (
    ...     'Illegal query parameters: "x", "zz". ' +
    ...     'Required but missing query parameters: "\\u0118", "b".')
    True
    >>> exc.illegal_keys == {'zz', 'x'}
    True
    >>> exc.missing_keys == {'Ę', 'b'}
    True
    >>> del exc
    """

    illegal_keys_msg_template = u'Illegal query parameters: {}.'
    missing_keys_msg_template = u'Required but missing query parameters: {}.'

    @property
    def default_public_message(self):
        """The aforementioned property."""
        messages = []
        if self.illegal_keys:
            messages.append(self.illegal_keys_msg_template.format(
                u', '.join(sorted('"{}"'.format(ascii_str(k))
                                  for k in self.illegal_keys))))
        if self.missing_keys:
            messages.append(self.missing_keys_msg_template.format(
                u', '.join(sorted('"{}"'.format(ascii_str(k))
                                  for k in self.missing_keys))))
        return u' '.join(messages)


class ParamValueCleaningError(_ValueCleaningErrorMixin, ParamCleaningError):
    r"""
    Raised when query parameter value(s) cannot be cleaned (are not valid).

    Especially, this exception should be raised by the *data
    specification* machinery (in particular, it is raised in
    :meth:`n6sdk.data_spec.BaseDataSpec.clean_param_dict`) when any
    :exc:`~exceptions.Exception` subclass(es)/instance(s) (possibly,
    :exc:`FieldValueError`) have been *caught after being raised by data
    specification fields'* :meth:`~.Field.clean_param_value`.

    This exception class provides :attr:`default_public_message` (see:
    :exc:`_ErrorWithPublicMessageMixin`) as a property whose value is a
    nice, user-readable message that includes, *for each contained
    exception*: the key, the offending value(s) and the
    :attr:`public_message` attribute of that *contained exception* (the
    latter only for instances of :exc:`_ErrorWithPublicMessageMixin`
    subclasses).

    >>> err1 = TypeError('foo', 'bar')
    >>> err2 = FieldValueError('foo', 'bar', public_message='Message.')
    >>> try:
    ...     raise ParamValueCleaningError([
    ...         ('k1', 'ł-1', err1),
    ...         ('k2', ['ł-2', 'xyz'], err2),
    ...     ])
    ... except ParamCleaningError as e:
    ...     exc = e
    ...
    >>> exc.public_message == (
    ...     'Problem with value(s) ("\\u0142-1") of query parameter "k1". ' +
    ...     'Problem with value(s) ("\\u0142-2", "xyz")' +
    ...     ' of query parameter "k2" (Message).')
    True
    >>> exc.error_info_seq == [
    ...     ('k1', 'ł-1', err1),
    ...     ('k2', ['ł-2', 'xyz'], err2),
    ... ]
    True
    >>> del exc
    """

    msg_template = (u'Problem with value(s) ({values_repr}) of query '
                    u'parameter "{key}"{optional_exc_public_message}.')

    @property
    def default_public_message(self):
        """The aforementioned property."""
        messages = []
        for key, values, exc in self.error_info_seq:
            if isinstance(values, basestring):                                   #3: `basestring`->`str`
                values = (values,)
            assert isinstance(values, collections_abc.Sequence)
            msg = self.msg_template.format(
                key=ascii_str(key),
                values_repr=u', '.join(
                    u'"{}"'.format(ascii_str(val))
                    for val in values),
                optional_exc_public_message=(
                    u' ({})'.format(exc.public_message.rstrip(u'.'))
                    if isinstance(exc, _ErrorWithPublicMessageMixin)
                    else u''))
            messages.append(msg)
        return u' '.join(messages)


class ResultCleaningError(DataAPIError):
    """
    The base class for exceptions (to be treated as "HTTP-500-like"
    ones) raised when result data cleaning fails.

    Instances of its subclasses are raised by the *data specification*
    machinery.

    .. note::

       :attr:`default_public_message` (see:
       :exc:`_ErrorWithPublicMessageMixin`) is consciously left as the
       default and safe ``u'Internal error.'``.
    """


class ResultKeyCleaningError(_KeyCleaningErrorMixin, ResultCleaningError):
    """
    This exception should be raised by the *data specification*
    machinery (in particular, it is raised in
    :meth:`n6sdk.data_spec.BaseDataSpec.clean_result_dict`) when some
    keys in a data-backend-API-produced *result dictionary* are illegal
    and/or missing.

    .. note::

       :attr:`default_public_message` (see:
       :exc:`_ErrorWithPublicMessageMixin`) is consciously left as the
       default and safe ``u'Internal error.'``.
    """


class ResultValueCleaningError(_ValueCleaningErrorMixin, ResultCleaningError):
    """
    Raised when result item value(s) cannot be cleaned (are not valid).

    Especially, this exception should be raised by the *data
    specification* machinery (in particular, it is raised in
    :meth:`n6sdk.data_spec.BaseDataSpec.clean_result_dict`) when any
    :exc:`~exceptions.Exception` subclass(es)/instance(s) have been
    *caught after being raised by data specification fields'*
    :meth:`~.Field.clean_result_value`.

    .. note::

       :attr:`default_public_message` (see:
       :exc:`_ErrorWithPublicMessageMixin`) is consciously left as the
       default and safe ``u'Internal error.'`` -- so (**unlike** for
       :exc:`ParamValueCleaningError` and fields'
       :meth:`~.Field.clean_param_value`) no information from underlying
       :exc:`FieldValueError` or other exceptions raised in fields'
       :meth:`~.Field.clean_result_value` is disclosed in the
       :attr:`default_public_message` value.
    """
