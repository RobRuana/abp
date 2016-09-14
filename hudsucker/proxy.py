# Copyright (c) 2016 Rob Ruana
# Licensed under the MIT License, see LICENSE for details.

from __future__ import absolute_import
import os
import six

from collections import OrderedDict
from difflib import SequenceMatcher
from lxml import html
from math import ceil, floor
from PIL import Image, ImageChops, ImageEnhance

from hudsucker.industries import (
    chunks,
    circular_iter,
    filesystem_safe,
    is_imageish,
    is_urlish,
    log,
    scale_to_fit,
    split_url_filename,
    url_filename,
    DownloadCache)


class CardInfo(object):

    @classmethod
    def parse(cls, file_path):
        with open(file_path) as file:
            lines = [line.partition('#')[0].strip() for line in file]
            return [cls(line) for line in lines if line]

    def __init__(self, card):
        self.raw = card
        if is_urlish(card):
            self.name, _ = split_url_filename(card)
            if is_imageish(card):
                self.html_url = None
                self.image_url = card
            else:
                self.html_url = card
                self.image_url = None
        else:
            self.name = card
            self.html_url = None
            self.image_url = None
        self.image_basename = filesystem_safe(self.raw)

    def guess_filename(self):
        if self.image_url:
            return url_filename(self.image_url)
        elif self.html_url:
            return url_filename(self.html_url)
        else:
            return filesystem_safe(self.name)


class HulaHoop(object):

    search_engines = OrderedDict([
        ('ask', ('http://www.ask.com/web?q=', 'a')),
        ('bing', ('http://www.bing.com/search?q=', 'a')),
        ('duckduckgo', ('https://duckduckgo.com/html/?q=', 'a')),
        ('yahoo', ('https://search.yahoo.com/search?p=', 'a'))])

    search_engines_round_robin = circular_iter(list(search_engines.keys()))

    def __init__(self, border, quality, resolution, site, output_dir, cache_dir, no_cache, refresh_cache):
        self.quality = quality
        self.resolution = resolution
        self.site = site
        self.output_dir = output_dir
        self.cache_dir = os.path.join(cache_dir, '_download_cache_')
        self.no_cache = no_cache
        self.refresh_cache = refresh_cache
        self.cache = None  # Cache is initialized in run() method

        # Empirically determined inner card size: 2.24 inches, 3.24 inches
        border = round(border * resolution * 2.0) / 2.0
        self.border_leading = int(floor(border))
        self.border_trailing = int(ceil(border))
        self.inner_card_width = int(round(2.4 * resolution))
        self.inner_card_height = int(round(3.4 * resolution))
        self.outer_card_width = int(self.inner_card_width + self.border_leading + self.border_trailing)
        self.outer_card_height = int(self.inner_card_height + self.border_leading + self.border_trailing)

    def _crop_border(self, image):
        bright_image = ImageEnhance.Brightness(image).enhance(2)
        bg = Image.new(image.mode, image.size, image.getpixel((int(round(image.width / 2.0)), 0)))
        diff = ImageChops.difference(bright_image, bg)
        diff = ImageChops.add(diff, diff, 1, -100)
        bbox = diff.getbbox()
        return image.crop(bbox)

    def _image_file_for_card(self, card):
        cache_path = self.cache.get_cached_file(card.image_basename)
        if cache_path:
            log('Using cached image: {}'.format(cache_path))
            return cache_path

        log()
        indention = log.indention
        if not card.image_url:
            if not card.html_url:
                log('Searching for "{}" on {}...'.format(card.name, self.site))
                card.html_url = self._search_for_card(card)
                log.indention += 4

            log('Looking for image in: {}'.format(card.html_url))
            card.image_url = self._image_url_from_html(card)
            log.indention += 4

        log('Downloading: {}'.format(card.image_url))
        with log.indent(blank_line=True, exit_indention=indention):
            return self.cache.get_file(card.image_url, cache_basename=card.image_basename)

    def _images_for_cards(self, cards):
        images = []
        for card in cards:
            image_path = self._image_file_for_card(card)
            if image_path:
                images.append((Image.open(image_path), card))
            else:
                six.print_('')
                six.print_('Could not find image for: "{}"'.format(card.raw))
                six.print_('')
        return images

    @log.auto_indent()
    def _image_url_from_html(self, card):
        text = self.cache.get_text(card.html_url)
        if not text:
            return None
        doc = html.fromstring(text)
        urls = [m.get('content').strip() for m in doc.cssselect('meta') if m.get('property') == 'og:image']
        image_url = urls[0] if urls else None
        image_path_url, _, _ = card.html_url.rpartition('/')
        if image_url:
            if image_url.startswith('http'):
                log('Found image url in meta tag: {}'.format(image_url))
            else:
                log('Found relative image url in meta tag: {}'.format(image_url))
                image_url = '{}/{}'.format(image_path_url, image_url)
        else:
            urls = OrderedDict()
            for i in doc.cssselect('img'):
                src = i.get('src', '').strip()
                if src:
                    urls[src] = i.get('alt', '').strip()

            log('Didn\'t find image url in meta tag, searching html...')
            image_url = self._url_matching_card(card, urls)
            if not image_url:
                image_url = '{}/{}.jpg'.format(image_path_url, card.guess_filename())
                log('Didn\'t find image url in html, guessing: {}'.format(image_url))
        return image_url

    def _process_card_file(self, input_path):
        cards = CardInfo.parse(input_path)

        sheet_basename, _ = os.path.splitext(os.path.basename(input_path))
        sheets = []
        for (sheet_index, sheet) in enumerate(chunks(self._images_for_cards(cards), 9)):
            cropped_images = []
            for (image, card) in sheet:
                cropped_image = self._crop_border(image)
                cropped_images.append((cropped_image, card))

            card_count = len(sheet)
            sheet_width = self.outer_card_width * min(3.0, card_count)
            sheet_height = self.outer_card_height * ceil(card_count / 3.0)

            sheet_filename = '{}{:02d}.pdf'.format(sheet_basename, sheet_index + 1)
            sheet_path = os.path.join(self.output_dir, sheet_filename)
            sheet_image = Image.new('RGB', (int(sheet_width), int(sheet_height)), 'white')

            for (card_index, (image, card)) in enumerate(cropped_images):
                if image.width != self.inner_card_width or image.height != self.inner_card_height:
                    new_width, new_height = scale_to_fit(image.size, (self.inner_card_width, self.inner_card_height))
                    new_width, new_height = int(ceil(new_width)), int(ceil(new_height))
                    if new_width != image.width and new_height != image.height:
                        image = image.resize((new_width, new_height), Image.LANCZOS)

                inner_card_x = max(self.border_leading, floor((self.outer_card_width - image.width) / 2.0))
                inner_card_y = max(self.border_leading, floor((self.outer_card_height - image.height) / 2.0))
                border_image = Image.new('RGB', (self.outer_card_width, self.outer_card_height), 'black')
                border_image.paste(image, (int(inner_card_x), int(inner_card_y)))

                outer_card_x = self.outer_card_width * (card_index % 3.0)
                outer_card_y = self.outer_card_height * floor(card_index / 3.0)
                sheet_image.paste(border_image, (int(outer_card_x), int(outer_card_y)))

            log('\nSaving: {}\n'.format(sheet_path))
            sheets.append(sheet_path)
            sheet_image.save(sheet_path, 'PDF', quality=self.quality,
                             resolution=self.resolution, resolution_unit='inch')
        return sheets

    @log.auto_indent()
    def _search_for_card(self, card):
        for engine in self.search_engines_round_robin:
            url, css_selector = self.search_engines[engine]
            text = self.cache.get_text(url, '{} site:{}'.format(card.name, self.site))
            if text:
                doc = html.fromstring(text)
                urls = OrderedDict()
                for a in doc.cssselect(css_selector):
                    href = a.get('href', '').strip()
                    if href and href.startswith('http') and self.site in href and href not in urls:
                        urls[href] = a.text_content().strip()

                result = self._url_matching_card(card, urls)
                if result:
                    return result
        return None

    def _url_matching_card(self, card, urls, threshold=0.7):
        results = []
        source_filename = split_url_filename(card.guess_filename())[0].lower()
        image_filename = card.image_basename.lower()
        card_name = card.name.lower()
        for (url, text) in urls.items():
            text = text.lower()
            url_filename = split_url_filename(url)[0].lower()
            image_ratio = SequenceMatcher(None, image_filename, url_filename).ratio()
            source_ratio = SequenceMatcher(None, source_filename, url_filename).ratio()
            if card_name in text:
                card_ratio = 0.9
            else:
                card_ratio = SequenceMatcher(None, card_name, text).ratio()
            ratio = max(image_ratio, card_ratio, source_ratio)
            if ratio >= threshold:
                results.append((url, ratio))

        log('Found {} result{}:'.format(len(results), '' if len(results) == 1 else 's'))
        matching_result = None
        matching_ratio = 0
        for (result, ratio) in results:
            with log.indent():
                log('{} (Matches {:.2f}%)'.format(result, ratio * 100))
            if ratio > matching_ratio:
                matching_result = result
                matching_ratio = ratio
        if len(results) > 1:
            log('Using closest matching result: {}'.format(matching_result))

        return matching_result

    def run(self, input_paths):
        if not os.path.exists(self.output_dir):
            log('Creating output dir: {}\n'.format(self.output_dir))
            os.makedirs(self.output_dir)

        self.cache = DownloadCache(self.cache_dir, self.refresh_cache, self.no_cache, '_hudsucker_cache_')
        with self.cache.auto_cleanup():
            sheets = []
            for input_path in input_paths:
                sheets.extend(self._process_card_file(input_path))
            for sheet in sheets:
                six.print_(sheet)
