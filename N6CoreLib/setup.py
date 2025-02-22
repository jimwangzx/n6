# Copyright (c) 2013-2021 NASK. All rights reserved.

import glob
import os
import os.path as osp
import sys

from setuptools import setup, find_packages


setup_dir, setup_filename = osp.split(osp.abspath(__file__))
setup_human_readable_ref = osp.join(osp.basename(setup_dir), setup_filename)

venv_dir = os.environ.get('VIRTUAL_ENV')

def get_n6_version(filename_base):
    path_base = osp.join(setup_dir, filename_base)
    path_glob_pattern = path_base + '*'
    # The non-suffixed path variant should be
    # tried only if another one does not exist.
    matching_paths = sorted(glob.iglob(path_glob_pattern),
                            reverse=True)
    try:
        path = matching_paths[0]
    except IndexError:
        sys.exit('[{}] Cannot determine the n6 version '
                 '(no files match the pattern {!r}).'
                 .format(setup_human_readable_ref,
                         path_glob_pattern))
    try:
        with open(path) as f:                                             #3: add: `, encoding='ascii'`
            return f.read().strip()
    except (OSError, UnicodeError) as exc:
        sys.exit('[{}] Cannot determine the n6 version '
                 '(an error occurred when trying to '
                 'read it from the file {!r} - {}).'
                 .format(setup_human_readable_ref,
                         path,
                         exc))

def setup_data_line_generator(filename_base):
    path_base = osp.join(setup_dir, filename_base)
    path_glob_pattern = path_base + '*'
    # Here we sort the paths just to make the order of operations deterministic.
    matching_paths = sorted(glob.iglob(path_glob_pattern))
    for path in matching_paths:
        try:
            with open(path) as f:                                         #3: add: `, encoding='ascii'`
                for raw_line in f:
                    yield raw_line.strip()
        except (OSError, UnicodeError) as exc:
            sys.exit('[{}] Could not read from the file {!r} ({})'
                     .format(setup_human_readable_ref, path, exc))


n6_version = get_n6_version('.n6-version')

pip_install = False
setup_install = False
requirements = [
    'n6sdk-py2==' + n6_version,
    'n6lib-py2==' + n6_version,
]
requirements_pip = []
dep_links = []
for line in setup_data_line_generator('requirements'):
    if line == '# pip install section':
        pip_install = True
        setup_install = False
    elif line == '# setuptools install section':
        setup_install = True
        pip_install = False
    if not line or line.startswith('#'):
        continue
    if setup_install:
        req = line.split('\t')
        requirements.append(req[0])
        try:
            dep_links.append(req[1])
        except IndexError:
            pass
    elif pip_install:
        requirements_pip.append(line)


setup(
    name="n6corelib-py2",
    version=n6_version,

    packages=find_packages(),
    include_package_data=True,
    python_requires='==2.7.*',
    zip_safe=False,
    tests_require=["mock==3.0.5", "unittest_expander==0.3.1"],
    test_suite="n6corelib.tests",
    dependency_links=dep_links,
    install_requires=requirements,
    #entry_points={
    #  'console_scripts': [
    #  ],
    #},

    description='The library of common *n6* modules **not yet migrated to Python 3.x**',
    url='https://github.com/CERT-Polska/n6',
    maintainer='CERT Polska',
    maintainer_email='n6@cert.pl',
    classifiers=[
        'License :: OSI Approved :: GNU Affero General Public License v3',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Topic :: Security',
    ],
    keywords='n6 network incident exchange',
)

for pkgname in requirements_pip:
    if venv_dir:
        command = "{}/bin/pip install '{}'".format(venv_dir, pkgname)
    else:
        command = "/usr/bin/pip install '{}'".format(pkgname)
    if os.system(command):
        sys.exit('[{}] Exiting after an error when executing the command: '
                 '{!r}.'.format(setup_human_readable_ref, command))
