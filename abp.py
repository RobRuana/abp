#!/usr/bin/env python

# MIT License
#
# Copyright (c) 2016 Rob Ruana
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
'''
# Example input file, comments and blank lines are supported

# Cards names are listed one per line, misspellings are okay
Pia Nalaar              # Inline comments are also supported
Saheeli's Artistry      # Spaces, capitals, and punctuation are fine

# For multiples of the same card, list them multiple times
Strip Mine
Strip Mine

# The page for the card can be specified
http://mythicspoiler.com/kld/cards/wispweaverangel.html

# Or the image file can be listed explicitly
http://mythicspoiler.com/kld/cards/trinketmastercraft.jpg
http://www.mythicspoiler.com/kld/cards/gontilordofluxury.jpg

# Sites other than mythicspoiler.com can be specified
# A best attempt will be made to determine the card image
http://magiccards.info/vma/en/4.html # Black Lotus

# Image files from any site can also be listed explicitly
http://magiccards.info/scans/en/vma/1.jpg # Ancestral Recall

'''

import argparse
import glob
import os
import re
import requests
import shutil
import tempfile
import time

import six
from collections import OrderedDict
from contextlib import contextmanager
from difflib import SequenceMatcher

from lxml import html
from math import ceil, floor
from PIL import Image, ImageChops, ImageEnhance
from six.moves.urllib.parse import quote, unquote_plus, urlparse


parser = argparse.ArgumentParser(description='A.B.P. Always Be Proxying. Generate proxy sheets from mythicspoiler.com')
parser.add_argument('input', metavar='FILE', nargs='+', help='each line of FILE should be a MtG card name, or a url')
parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', help='print verbose details')
output_group = parser.add_argument_group('card output arguments')
output_group.add_argument('-m', '--margin', dest='margin', metavar='N', default=3, type=float , help='border width as a percent of card width, defaults to 3')
output_group.add_argument('-o', '--output', dest='output_dir', metavar='DIR', default='.', help='output dir, defaults to current dir')
output_group.add_argument('-p', '--resolution', dest='resolution', metavar='N', default=600.0, type=float , help='print resolution of output PDF, defaults to 600')
output_group.add_argument('-s', '--site', dest='site', metavar='URL', default='mythicspoiler.com', help='site to search for card images, defaults to mythicspoiler.com')
cache_group = parser.add_argument_group('caching arguments', description='NOTE: Careful turning off cache, search engines may ban your IP')
cache_group.add_argument('-c', '--cache', dest='cache_dir', metavar='DIR', default='abp_cache', help='cache dir, defaults to abp_cache')
cache_group.add_argument('-n', '--no-cache', dest='no_cache', action='store_true', help='don\'t cache any downloaded files')
cache_group.add_argument('-r', '--refresh', dest='refresh', action='store_true', help='force refresh of any cached downloads')
args = parser.parse_args()


class RoundRobinIter(object):
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


search_engines = OrderedDict([
    ('ask', ('http://www.ask.com/web?q=', 'a')),
    ('bing', ('http://www.bing.com/search?q=', 'a')),
    ('duckduckgo', ('https://duckduckgo.com/html/?q=', 'a')),
    ('yahoo', ('https://search.yahoo.com/search?p=', 'a'))])

search_engines_round_robin = RoundRobinIter(list(search_engines.keys()))


# Only prints when --verbose
def log(*s, **kw):
    if args.verbose:
        six.print_(*s, **kw)

def chunks(iterable, size=2):
    return [iterable[x:x + size] for x in range(0, len(iterable), size)]

def scale_to_fit(width, height, bounds_width, bounds_height):
    if width <= 0:
        return (width, min(height, bounds_height))
    if height <= 0:
        return (min(width, bounds_width), height)
    # get true-division on python 2
    scale = min(float(bounds_width) / width, float(bounds_height) / height)
    return (width * scale, height * scale)

# Context manager that creates appropriate download directory
def create_download_dir():
    if args.no_cache:
        return tempfile.TemporaryDirectory()
    else:
        @contextmanager
        def _create_download_dir():
            cache_dir = os.path.abspath(os.path.expanduser(args.cache_dir))
            if not os.path.exists(cache_dir):
                log('Creating download cache dir: {}\n'.format(cache_dir))
                os.makedirs(cache_dir)
            yield cache_dir
        return _create_download_dir()

def card_to_filename(card):
    if card.startswith('http'):
        card, _ = parse_url_filename(card)
    return re.sub(r'\W', '', card.encode('ascii', 'ignore').decode('utf-8').lower())

def string_to_filename(s):
    return re.sub(r'[^\w\.]', '', s.encode('ascii', 'ignore').decode('utf-8').lower())

def parse_url_filename(url):
    if url:
        return os.path.splitext(os.path.basename(urlparse(url).path))
    return '', ''

def parse_cards(file):
    lines = [line.partition('#')[0].strip() for line in file]
    return [(card, card_to_filename(card)) for card in lines if card]

def purge_cache(download_dir):
    for cache_dir in glob.glob(os.path.join(download_dir, '*_cache')):
        if os.path.exists(cache_dir):
            log('Deleting cache dir: {}'.format(cache_dir))
            shutil.rmtree(cache_dir)

def cached_image(filename, download_dir):
    cache_dir = os.path.join(download_dir, filename + '_cache')
    glob_exp = filename + '.*'
    files = glob.glob(os.path.join(cache_dir, glob_exp))
    if files:
        return files[0]
    return None

def cached_download(url, filename, download_dir, query='', cache_filename=None):
    if not url:
        return None
    log('    GET \'{}{}\''.format(url, query))
    query_url = url + quote(query)

    cache_dir = os.path.join(download_dir, filename + '_cache')
    if not os.path.exists(cache_dir):
        log('        Creating cache dir: {}'.format(cache_dir))
        os.makedirs(cache_dir)
    if cache_filename:
        _, ext = parse_url_filename(url)
        cache_filename = '{}{}'.format(cache_filename, ext)
    else:
        cache_filename = string_to_filename(query_url)
    cache_file = os.path.join(cache_dir, cache_filename)

    if os.path.exists(cache_file):
        log('        Using cached file: {}'.format(cache_file))
    else:
        response = requests.get(query_url, stream=True)
        if response.ok:
            with open(cache_file, 'wb') as output:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk: # filter out keep-alive new chunks
                        output.write(chunk)
        else:
            cache_file = None
            six.print_('ERROR {} {}'.format(response.status_code, response.reason))
            six.print_(response.text)
        time.sleep(0.5)
    return cache_file

def cached_get(url, filename, download_dir, query=''):
    cache_file = cached_download(url, filename, download_dir, query)
    text = None
    if cache_file and os.path.exists(cache_file):
        with open(cache_file, 'r') as input:
            text = input.read()
    return text

def url_best_match(card, filename, source_url, urls, threshold=0.7):
    results = []
    source_filename, _ = parse_url_filename(source_url)
    for (url, text) in urls:
        url_filename, _ = parse_url_filename(url)
        filename_ratio = SequenceMatcher(None, filename, url_filename).ratio()
        source_ratio = SequenceMatcher(None, source_filename, url_filename).ratio()
        if card in text:
            card_ratio = 0.99
        else:
            card_ratio = SequenceMatcher(None, card, text).ratio()
        ratio = max(filename_ratio, card_ratio, source_ratio)
        if ratio >= threshold:
            results.append((url, ratio))

    log('        Found {} result{}'.format(len(results), '' if len(results) == 1 else 's'))
    matching_result = None
    matching_ratio = 0
    for (result, ratio) in results:
        log('            {} (Matches {:.2f}%)'.format(result, ratio * 100))
        if ratio > matching_ratio:
            matching_result = result
            matching_ratio = ratio
    if len(results) > 1:
        log('        Using closest matching result: {}'.format(matching_result))

    return matching_result

def search_for_card_with_engine(engine, card, filename, download_dir):
    url, css_selector = search_engines[engine]
    text = cached_get(url, filename, download_dir, '{} site:{}'.format(card, args.site))
    if not text:
        return None
    doc = html.fromstring(text)
    urls = OrderedDict()
    for a in doc.cssselect(css_selector):
        href = a.get('href', '').strip()
        if href.startswith('http') and args.site in href and href not in urls:
            urls[href] = a.text_content().strip()
    urls = [(href, text) for (href, text) in urls.items()]
    return url_best_match(card, filename, None, urls)

def search_for_card(card, filename, download_dir):
    for engine in search_engines_round_robin:
        result = search_for_card_with_engine(engine, card, filename, download_dir)
        if result:
            return result
    return None

def image_url_from_html(html_url, card, filename, download_dir):
    text = cached_get(html_url, filename, download_dir)
    if not text:
        return None
    doc = html.fromstring(text)
    urls = [m.get('content').strip() for m in doc.cssselect('meta') if m.get('property') == 'og:image']
    image_url = urls[0] if urls else None
    image_path_url, _, _ = html_url.rpartition('/')
    if image_url:
        if image_url.startswith('http'):
            log('    Found image url in meta tag: {}'.format(image_url))
        else:
            log('    Found relative image url in meta tag: {}'.format(image_url))
            image_url = '{}/{}'.format(image_path_url, image_url)
    else:
        urls = [(i.get('src').strip(), i.get('alt').strip()) for i in doc.cssselect('img') if i.get('src')]
        urls = OrderedDict([(url, True) for url in urls if url]).keys()
        log('    Didn\'t find image url in meta tag, searching html...')
        image_url = url_best_match(card, filename, html_url, urls)
        if not image_url:
            image_url = '{}/{}.jpg'.format(image_path_url, filename)
            log('    Didn\'t find image url in html, guessing: {}'.format(image_url))
    return image_url

def image_file_for_card(card, filename, download_dir):
    cache_file = cached_image(filename, download_dir)
    if cache_file:
        log('Using cached image: {}'.format(cache_file))
        return cache_file

    if card.startswith('http'):
        log('Checking {}'.format(card))
        if card.endswith('.html'):
            image_url = image_url_from_html(card, card, filename, download_dir)
        else:
            image_url = card
    else:
        log('Searching {} for "{}"...'.format(args.site, card))
        html_url = search_for_card(card, filename, download_dir)
        image_url = image_url_from_html(html_url, card, filename, download_dir)

    image_filename = cached_download(image_url, filename, download_dir, cache_filename=filename)
    log('')
    return image_filename

def images_for_cards(cards, download_dir):
    for (card, filename) in cards:
        image_file = image_file_for_card(card, filename, download_dir)
        if image_file:
            image = Image.open(image_file)
            yield (image, image_file, card, filename)
        else:
            six.print_('Could not find image for "{}"\n'.format(card))

def crop_border(image):
    bright_image = ImageEnhance.Brightness(image).enhance(2)
    bg = Image.new(image.mode, image.size, image.getpixel((0, 0)))
    diff = ImageChops.difference(bright_image, bg)
    diff = ImageChops.add(diff, diff, 1, -100)
    bbox = diff.getbbox()
    return image.crop(bbox)

def process_input_file(input_path, output_dir):
    sheets = []
    cards = []
    with open(input_path) as input_file:
        cards = parse_cards(input_file)

    # Empirically determined card size == (2.24 inches, 3.24 inches)
    inner_card_width = int(round(2.4 * args.resolution))
    inner_card_height = int(round(3.4 * args.resolution))
    sheet_basename, _ = os.path.splitext(os.path.basename(input_path))

    images = list(images_for_cards(cards, download_dir))
    for (sheet_index, sheet) in enumerate(chunks(images, 9)):
        cropped_images = []
        for (image, image_file, card, filename) in sheet:
            cropped_image = crop_border(image)
            cropped_images.append((cropped_image, image_file, card, filename))

        border = round(inner_card_width * (args.margin / 100.0) * 2.0) / 2.0
        border_leading = int(floor(border))
        border_trailing = int(ceil(border))
        outer_card_width = inner_card_width + border_leading + border_trailing
        outer_card_height = inner_card_height + border_leading + border_trailing
        card_count = len(sheet)
        sheet_width = outer_card_width * min(3.0, card_count)
        sheet_height = outer_card_height * ceil(card_count / 3.0)

        sheet_filename = '{}{:02d}.pdf'.format(sheet_basename, sheet_index + 1)
        sheet_path = os.path.join(output_dir, sheet_filename)
        sheet_image = Image.new('RGB', (int(sheet_width), int(sheet_height)), 'white')

        for (i, (image, image_file, card, filename)) in enumerate(cropped_images):
            if image.width != inner_card_width or image.height != inner_card_height:
                new_width, new_height = scale_to_fit(image.width, image.height, inner_card_width, inner_card_height)
                new_width, new_height = ceil(new_width), ceil(new_height)
                if new_width != image.width and new_height != image.height:
                    image = image.resize((int(new_width), int(new_height)), Image.LANCZOS)

            border_image = Image.new('RGB', (int(outer_card_width), int(outer_card_height)), 'black')
            inner_card_x = max(border_leading, floor((outer_card_width - image.width) / 2.0))
            inner_card_y = max(border_leading, floor((outer_card_height - image.height) / 2.0))
            border_image.paste(image, (int(inner_card_x), int(inner_card_y)))

            outer_card_x = outer_card_width * (i % 3.0)
            outer_card_y = outer_card_height * floor(i / 3.0)
            sheet_image.paste(border_image, (int(outer_card_x), int(outer_card_y)))

        if not os.path.exists(output_dir):
            log('Creating output dir: {}\n'.format(output_dir))
            os.makedirs(output_dir)

        log('Saving: {}\n'.format(sheet_path))
        sheet_image.save(sheet_path, 'PDF', quality=95, resolution=args.resolution, resolution_unit='inch')
        sheets.append(sheet_filename)

    return sheets


with create_download_dir() as download_dir:
    if args.refresh:
        log('Purging cache because --refresh was specified')
        purge_cache(download_dir)
        log('')

    sheets = []
    output_dir = os.path.abspath(os.path.expanduser(args.output_dir))
    for input_path in args.input:
        sheets.extend(process_input_file(input_path, output_dir))

    for sheet in sheets:
        six.print_(os.path.join(args.output_dir, sheet))
