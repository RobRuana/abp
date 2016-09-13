#!/usr/bin/env python

# Copyright (c) 2016 Rob Ruana
# Licensed under the MIT License, see LICENSE for details.

from __future__ import absolute_import
import argparse
import os
import sys

from hudsucker.industries import log
from hudsucker.proxy import HulaHoop


def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = argparse.ArgumentParser(description='Hudsucker Proxy Generator - generate MtG proxy sheets')
    parser.add_argument('input', metavar='FILE', nargs='+',
                        help='each line of FILE should be a MtG card name, or a url')
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                        help='print verbose details')

    output_group = parser.add_argument_group('proxy sheet options')
    output_group.add_argument('-b', '--border', dest='border', metavar='N', default=0.072, type=float,
                              help='border width in inches, defaults to 0.072')
    output_group.add_argument('-o', '--output', dest='output_dir', metavar='DIR', default='.',
                              help='output dir, defaults to current dir')
    output_group.add_argument('-p', '--resolution', dest='resolution', metavar='N', default=600.0, type=float,
                              help='print resolution of output PDF, defaults to 600')
    output_group.add_argument('-q', '--quality', dest='quality', metavar='N', default=95, type=int,
                              help='quality to use for JPEG encoding, defaults to 95')
    output_group.add_argument('-s', '--site', dest='site', metavar='URL', default='mythicspoiler.com',
                              help='site to search for card images, defaults to mythicspoiler.com')

    cache_group = parser.add_argument_group('caching options', description='NOTE: '
                                            'Careful turning off cache, search engines may ban your IP')
    cache_group.add_argument('-c', '--cache', dest='cache_dir', metavar='DIR', default='hudsucker_cache',
                             help='cache dir, defaults to hudsucker_cache')
    cache_group.add_argument('-n', '--no-cache', dest='no_cache', action='store_true',
                             help='don\'t cache any downloaded files')
    cache_group.add_argument('-r', '--refresh', dest='refresh_cache', action='store_true',
                             help='force refresh of any cached downloads')

    args = parser.parse_args(argv[1:])

    log.verbose = args.verbose

    hula_hoop = HulaHoop(
        border=args.border,
        quality=min(95, max(1, args.quality)),
        resolution=args.resolution,
        site=args.site,
        output_dir=os.path.expanduser(args.output_dir),
        cache_dir=os.path.expanduser(args.cache_dir),
        no_cache=args.no_cache,
        refresh_cache=args.refresh_cache)

    hula_hoop.run(args.input)


if __name__ == '__main__':
    sys.exit(main())
