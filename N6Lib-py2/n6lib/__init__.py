# Copyright (c) 2020-2021 NASK. All rights reserved.

import atexit
import locale
import os

# Let's trigger the `n6sdk`-provided monkey-patching
# (if any and if not triggered yet).
import n6sdk                                                                   # noqa

from n6lib.common_helpers import cleanup_src
from n6lib.config import monkey_patch_configparser_to_provide_some_legacy_defaults
from n6lib.log_helpers import early_Formatter_class_monkeypatching

# Ensure that locale is set to 'C.UTF-8' (or a custom one if you decide
# to enforce it by setting the `N6_FORCE_LOCALE` environment variable;
# but first please read the notes below).
#
# Note:
#
# * The code of *n6* assumes that the locale settings affecting parsing
#   and formatting of date/time elements (for example, abbreviations of
#   month or week day names...) are C-locale-compliant. So it is
#   **important** that even if you decide to enforce your custom locale
#   (with the `N6_FORCE_LOCALE` environment variable) it **needs to be
#   C-locale-compliant in terms of date/time parsing and formatting!**
#
# * The code of *n6* assumes that the locale settings affecting I/O
#   encoding are UTF-8-compatible (that's why, by default, we employ
#   here 'C.UTF-8' and not bare 'C'). So it is **important** that
#   even if you decide to enforce your custom locale (with the
#   `N6_FORCE_LOCALE` environment variable) it **needs to be a
#   UTF-8-encoding-based one!**
locale_setting = os.environ.get('N6_FORCE_LOCALE') or 'C'                        #3: `C` -> `C.UTF-8`
locale.setlocale(locale.LC_ALL, locale_setting)

# Monkey-patch logging.Formatter to use UTC time.
early_Formatter_class_monkeypatching()

# Monkey-patch configparser.RawConfigParser (with its subclasses)...
monkey_patch_configparser_to_provide_some_legacy_defaults()

# Ensure that resource files and directories extracted with
# pkg_resources stuff are removed (or at least tried to be removed).
import logging  # <- Must be imported *before* registering cleanup_src().      # noqa
atexit.register(cleanup_src)
