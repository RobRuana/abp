# Copyright (c) 2016 Rob Ruana
# Licensed under the MIT License, see LICENSE for details.

from __future__ import absolute_import
import glob
import os
import re
import requests
import shutil
import six
import tempfile
import time

from contextlib import contextmanager
from functools import wraps
from six.moves.urllib.parse import quote, urlparse


def collapse_blank_lines(text, pre_count=1, post_count=1):
    pre_lines = []
    first_line, _, text_body = text.partition('\n')
    while not first_line.strip() and text_body:
        text = text_body
        if len(pre_lines) < pre_count:
            pre_lines.append(first_line)
        first_line, _, text_body = text.partition('\n')

    post_lines = []
    text_body, _, last_line = text.rpartition('\n')
    while not last_line.strip() and text_body:
        text = text_body
        if len(post_lines) < post_count:
            post_lines.append(last_line)
        text_body, _, last_line = text.rpartition('\n')

    return '\n'.join(pre_lines + [text] + post_lines)


def indent(text, prefix):
    def prefixed_lines():
        for line in text.splitlines(True):
            yield (prefix + line if line.strip() else line)
    return ''.join(prefixed_lines())


class VerbosityLogger(object):

    def __init__(self, verbose=False, collapse_blank_lines=True):
        self.verbose = verbose
        self.collapse_blank_lines = collapse_blank_lines
        self.has_blank_line = True
        self.indention = 0

    def __call__(self, message=''):
        if self.verbose:
            if self.collapse_blank_lines:
                pre_count = 0 if self.has_blank_line else 1
                message = collapse_blank_lines(message, pre_count)
                if self.has_blank_line and not message.strip():
                    return
            if self.indention > 0:
                six.print_(indent(message, ' ' * self.indention))
            else:
                six.print_(message)
            self.has_blank_line = message.rsplit('\n', 1)[-1].strip() == ''

    def auto_indent(self, n=4, blank_line=False):
        def outer(func):
            @wraps(func)
            def inner(*a, **kw):
                with self.indent(n, blank_line):
                    return func(*a, **kw)
            return inner
        return outer

    def auto_log(self, message=''):
        def outer(func):
            @wraps(func)
            def inner(*a, **kw):
                result = func(*a, **kw)
                self(message)
                return result
            return inner
        return outer

    @contextmanager
    def indent(self, n=4, blank_line=False):
        self.indention += n
        yield self
        self.indention -= n
        if blank_line:
            self()


log = VerbosityLogger()


def chunks(iterable, size=2):
    return [iterable[x:x + size] for x in range(0, len(iterable), size)]


class circular_iter(object):

    def __init__(self, indexable):
        self.nextIndex = 0
        self.stopIndex = -1
        self.indexable = indexable

    def __iter__(self):
        self.stopIndex = -1
        return self

    def next(self):
        return self.__next__()

    def __next__(self):
        if self.stopIndex == -1:
            self.stopIndex = self.nextIndex
        elif self.stopIndex == self.nextIndex:
            raise StopIteration()
        nextItem = self.indexable[self.nextIndex]
        self.nextIndex = (self.nextIndex + 1) % len(self.indexable)
        return nextItem


def filesystem_safe(s):
    return re.sub(r'[^\w\.\-_]+', '_', s.encode('ascii', 'ignore').decode('utf-8'))


def is_imageish(s):
    s = s.lower()
    return (s.endswith('.bmp') or s.endswith('.gif') or s.endswith('.jpg') or
            s.endswith('.jpeg') or s.endswith('.png') or s.endswith('.tga') or
            s.endswith('.tif') or s.endswith('.tiff') or s.endswith('.webp'))


def is_urlish(s):
    s = s.lower()
    return s.startswith('http') or (s.count('.') >= 2 and s.count('/') >= 1)


def scale_to_fit(size, bounds):
    width, height = size
    bounds_width, bounds_height = bounds
    if width <= 0:
        return (width, min(height, bounds_height))
    if height <= 0:
        return (min(width, bounds_width), height)
    # get true-division on python 2
    scale = min(float(bounds_width) / width, float(bounds_height) / height)
    return (width * scale, height * scale)


def split_url_filename(url):
    if url:
        return os.path.splitext(url_filename(url))
    return '', ''


def url_filename(url):
    if url:
        return os.path.basename(urlparse(url).path)
    return ''


class DownloadCache(object):

    def __init__(self, cache_dir, should_refresh, is_temp, temp_prefix='_download_cache_'):
        self.should_refresh = should_refresh
        self.is_temp = is_temp
        if is_temp:
            self.temp_dir = tempfile.mkdtemp(prefix=temp_prefix)
            self.cache_dir = self.temp_dir
            log('Using temp cache dir: {}\n'.format(self.cache_dir))
        else:
            self.temp_dir = None
            self.cache_dir = cache_dir
            if self.should_refresh:
                if os.path.exists(self.cache_dir):
                    log('Refreshing cache dir: {}\n'.format(self.cache_dir))
                    shutil.rmtree(self.cache_dir)
                    os.makedirs(self.cache_dir)
            if not os.path.exists(self.cache_dir):
                log('Creating cache dir: {}\n'.format(self.cache_dir))
                os.makedirs(self.cache_dir)

    @contextmanager
    def auto_cleanup(self):
        yield self
        self.cleanup()

    def cleanup(self):
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def get_cached_file(self, cache_basename):
        for file in glob.glob(os.path.join(self.cache_dir, cache_basename + '.*')):
            return file
        return None

    def get_file(self, url, query='', cache_basename=None):
        if not url:
            return None

        log('GET \'{}{}\''.format(url, query))
        query_url = url + quote(query)

        if cache_basename:
            _, ext = split_url_filename(url)
            cache_filename = '{}{}'.format(cache_basename, ext)
        else:
            cache_filename = filesystem_safe(query_url)
        cache_path = os.path.join(self.cache_dir, cache_filename)

        if os.path.exists(cache_path):
            with log.indent(): log('Using cached file: {}'.format(cache_path))
            return cache_path
        else:
            response = requests.get(query_url, stream=True)
            if response.ok:
                with open(cache_path, 'wb') as cache_file:
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:  # filter out keep-alive new chunks
                            cache_file.write(chunk)
            else:
                cache_path = None
                six.print_('')
                six.print_('ERROR {} {}'.format(response.status_code, response.reason))
                six.print_(response.text)
                six.print_('')

            # Take it easy on those servers out there :)
            time.sleep(0.5)
            return cache_path

    def get_text(self, url, query='', cache_basename=None):
        cache_path = self.get_file(url, query, cache_basename)
        text = None
        if cache_path and os.path.exists(cache_path):
            with open(cache_path, 'r') as cache_file:
                text = cache_file.read()
        return text
