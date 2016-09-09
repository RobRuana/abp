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
# Example input file, comments and blank lines are fine

# Cards names can be listed directly, one per line, misspellings are okay
Pia Nalaar              # In-line comments are also supported
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
import tempfile
import time

from collections import OrderedDict
from contextlib import contextmanager
from difflib import SequenceMatcher
from itertools import chain, islice, zip_longest
from lxml import html
from math import ceil, floor
from PIL import Image, ImageChops, ImageEnhance
from urllib.parse import quote, unquote_plus, urlparse


parser = argparse.ArgumentParser(description='A.B.P. Always Be Proxying. Generate proxy sheets from mythicspoiler.com')
parser.add_argument('input', type=open, metavar='FILE', help='each line of FILE should be a MtG card name, or a url')
parser.add_argument('-v, --verbose', dest='verbose', action='store_true', help='print verbose details')
parser.add_argument('-o, --output', dest='output_dir', metavar='DIR', default='.', help='output dir, defaults to current dir')
parser.add_argument('-m, --margin', dest='margin', metavar='PERCENT', default=3, type=float , help='border width as a percent of card width, defaults to 3')
cache_group = parser.add_argument_group('caching arguments', description='NOTE: Careful turning off cache, search engines may ban your IP')
cache_group.add_argument('-c, --cache', dest='cache_dir', metavar='DIR', default='abp_cache', help='cache dir, defaults to abp_cache')
cache_group.add_argument('-n, --no-cache', dest='no_cache', action='store_true', help='don\'t cache any downloaded files')
cache_group.add_argument('-r, --refresh', dest='refresh', action='store_true', help='force refresh of any cached downloads')
args = parser.parse_args()


class RoundRobinIter(object):
    def __init__(self, indexable):
        self.nextIndex = 0
        self.stopIndex = -1
        self.indexable = indexable
    def __iter__(self):
        self.stopIndex = -1
        return self
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
        print(*s, **kw)

def chunks(iterable, size=2):
    return [iterable[x:x + size] for x in range(0, len(iterable), size)]

def scale_to_fit(width, height, bounds_width, bounds_height):
    if width <= 0:
        return (width, min(height, bounds_height))
    if height <= 0:
        return (min(width, bounds_width), height)
    scale = min(bounds_width / width, bounds_height / height)
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
        card, _ = os.path.splitext(os.path.basename(unquote_plus(urlparse(card).path)))
    return re.sub(r'\W', '', card.encode('ascii', 'ignore').decode('utf-8').lower())

def parse_cards(file):
    lines = [line.partition('#')[0].strip() for line in file]
    return [(card, card_to_filename(card)) for card in lines if card]

def purge_cache(cards, download_dir):
    for (card, filename) in cards:
        for file in glob.glob(os.path.join(download_dir, '{}*'.format(filename))):
            log('Deleting cache file {}'.format(file))
            os.remove(file)

def find_cache(glob_exp, download_dir):
    files = glob.glob(os.path.join(download_dir, glob_exp))
    if files:
        return files[0]
    return None

def cached_download(url, filename, download_dir, query=''):
    cache_file = os.path.join(download_dir, filename)
    log('    GET \'{}{}\''.format(url, query))
    if os.path.exists(cache_file):
        log('        Using cached file: {}'.format(cache_file))
    else:
        response = requests.get(url + quote(query), stream=True)
        if response.ok:
            with open(cache_file, 'wb') as output:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk: # filter out keep-alive new chunks
                        output.write(chunk)
        else:
            cache_file = None
            print('ERROR {} {}'.format(response.status_code, response.reason))
            print(response.text)
        time.sleep(0.5)
    return cache_file

def cached_get(url, query, filename, download_dir):
    cache_file = cached_download(url, filename, download_dir, query)
    text = None
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as input:
            text = input.read()
    return text

def url_best_match(filename, urls, threshold):
    results = []
    for url in urls:
        url_filename, _ = os.path.splitext(os.path.basename(urlparse(url).path))
        ratio = SequenceMatcher(None, filename, url_filename).ratio()
        if ratio >= 0.5:
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
    text = cached_get(url, '"{}" site:mythicspoiler.com'.format(card), '{}_{}_search.html'.format(filename, engine), download_dir)
    if not text:
        return None
    doc = html.fromstring(text)
    urls = [a.get('href').strip() for a in doc.cssselect(css_selector) if a.get('href')]
    urls = OrderedDict([(url, True) for url in urls if url]).keys()
    return url_best_match(filename, urls, 0.5)

def search_for_card(card, filename, download_dir):
    for engine in search_engines_round_robin:
        result = search_for_card_with_engine(engine, card, filename, download_dir)
        if result:
            return result
    return None

def image_url_from_html(html_url, filename, download_dir):
    html_filename = filename + '_html.html'
    text = cached_get(html_url, '', html_filename, download_dir)
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
        urls = [i.get('src').strip() for i in doc.cssselect('img') if i.get('src')]
        urls = OrderedDict([(url, True) for url in urls if url]).keys()
        log('    Didn\'t find image url in meta tag, searching html...')
        image_url = url_best_match(filename, urls, 0.5)
        if not image_url:
            image_url = '{}/{}.jpg'.format(image_path_url, filename)
            log('    Didn\'t find image url in html, guessing: {}'.format(image_url))
    return image_url

def image_file_for_card(card, filename, download_dir):
    cache_file = find_cache(filename + '.*', download_dir)
    if cache_file:
        return cache_file

    if card.startswith('http'):
        log('Checking {}'.format(card))
        if card.endswith('.html'):
            image_url = image_url_from_html(card, filename, download_dir)
        else:
            image_url = card
    else:
        log('Searching mythicspoiler.com for "{}"...'.format(card))
        html_url = search_for_card(card, filename, download_dir)
        image_url = image_url_from_html(html_url, filename, download_dir)

    image_filename = os.path.basename(urlparse(image_url).path)
    image_filename = cached_download(image_url, image_filename, download_dir)
    log('')
    return image_filename

def images_for_cards(cards, download_dir):
    for (card, filename) in cards:
        image_file = image_file_for_card(card, filename, download_dir)
        if image_file:
            image = Image.open(image_file)
            yield (image, image_file, card, filename)
        else:
            print('Could not find image for "{}"'.format(card))

def crop_border(image):
    bright_image = ImageEnhance.Brightness(image).enhance(2)
    bg = Image.new(image.mode, image.size, image.getpixel((0, 0)))
    diff = ImageChops.difference(bright_image, bg)
    diff = ImageChops.add(diff, diff, 1, -100)
    bbox = diff.getbbox()
    return image.crop(bbox)


output_dir = os.path.abspath(os.path.expanduser(args.output_dir))

with create_download_dir() as download_dir:
    cards = parse_cards(args.input)

    if args.refresh:
        log('Purging cache because --refresh was specified')
        purge_cache(cards, download_dir)
        log('')

    images = list(images_for_cards(cards, download_dir))
    for (sheet_index, sheet) in enumerate(chunks(images, 9)):
        inner_card_width = 0
        inner_card_height = 0
        cropped_images = []
        for (image, image_file, card, filename) in sheet:
            cropped_image = crop_border(image)
            cropped_images.append((cropped_image, image_file, card, filename))
            if cropped_image.width > inner_card_width:
                inner_card_width = cropped_image.width
            if cropped_image.height > inner_card_height:
                inner_card_height = cropped_image.height

        border = round(inner_card_width * (args.margin / 100.0) * 2.0) / 2.0
        border_leading = int(floor(border))
        border_trailing = int(ceil(border))
        outer_card_width = inner_card_width + border_leading + border_trailing
        outer_card_height = inner_card_height + border_leading + border_trailing
        card_count = len(sheet)
        sheet_width = outer_card_width * min(3, card_count)
        sheet_height = outer_card_height * ceil(card_count / 3)

        # Empirically determined card size == (2.24 inches, 3.24 inches)
        dpi = '{0:.2f}'.format(min(inner_card_width / 2.24, inner_card_height / 3.24))
        sheet_name = 'Sheet{:02d}_{}dpi.png'.format(sheet_index + 1, dpi)
        sheet_filename = os.path.join(output_dir, sheet_name)
        sheet_image = Image.new('RGB', (sheet_width, sheet_height), 'white')

        for (i, (image, image_file, card, filename)) in enumerate(cropped_images):
            if image.width != inner_card_width or image.height != inner_card_height:
                new_width, new_height = scale_to_fit(image.width, image.height, inner_card_width, inner_card_height)
                new_width, new_height = ceil(new_width), ceil(new_height)
                if new_width != image.width and new_height != image.height:
                    image = image.resize((new_width, new_height), Image.LANCZOS)
            border_image = Image.new('RGB', (outer_card_width, outer_card_height), 'black')
            inner_card_x = max(border_leading, floor((outer_card_width - image.width) / 2.0))
            inner_card_y = max(border_leading, floor((outer_card_height - image.height) / 2.0))
            border_image.paste(image, (inner_card_x, inner_card_y))

            outer_card_x = outer_card_width * (i % 3)
            outer_card_y = outer_card_height * floor(i / 3)
            sheet_image.paste(border_image, (outer_card_x, outer_card_y))

        if not os.path.exists(output_dir):
            log('Creating output dir: {}\n'.format(output_dir))
            os.makedirs(output_dir)

        print(os.path.join(args.output_dir, sheet_name))
        sheet_image.save(sheet_filename)