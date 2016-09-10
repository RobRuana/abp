# -*- coding: utf-8 -*-
# Copyright (c) 2016 Rob Ruana
# Licensed under the MIT License, see LICENSE for details.

"""Hudsucker Proxy Generator

Generate MtG proxy sheets from mythicspoiler.com & other sites.

"""

import os
from setuptools import setup, find_packages


# Package versioning solution originally found here:
# http://stackoverflow.com/q/458550
exec(open('_version.py').read())

reqs = open('requirements.txt', 'r').read().strip().splitlines()

setup(
    name='hudsucker',
    version=__version__,
    url='https://github.com/RobRuana/hudsucker',
    download_url='http://pypi.python.org/pypi/hudsucker',
    license='MIT',
    author='Rob Ruana',
    author_email='rob@robruana.com',
    description=__doc__,
    long_description=open('README.rst', 'r').read(),
    zip_safe=True,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
        'Topic :: Utilities',
    ],
    platforms='any',
    packages=find_packages(),
    install_requires=reqs,
    tests_require=reqs,
    entry_points={
        'console_scripts': ['hudsucker = hudsucker:main']
    },
)
