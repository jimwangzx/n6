#!/usr/bin/python

# Let's apply n6 specific monkey-patching as early as possible.
import n6lib  # noqa

from pyramid.paster import get_app, setup_logging
#os.environ['N6_PORTAL_AUTH_2021'] = '1'
ini_path = '/home/dataman/n6/etc/web/conf/portal.ini'
setup_logging(ini_path)
application = get_app(ini_path, 'main')
