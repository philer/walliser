# -*- coding: utf-8 -*-

import os
import subprocess
import builtins
import logging
from operator import attrgetter
from random import shuffle
from glob import iglob as glob
import re
from datetime import datetime

from PIL import Image

from .util import (Observable, observed, observed_property,
                   get_file_hash, parse_relative_time)
from .progress import progress

import warnings
warnings.simplefilter('error', Image.DecompressionBombWarning)
Image.MAX_IMAGE_PIXELS = 16000**2

log = logging.getLogger(__name__)


def find_images(patterns):
    """Returns an iterable of wallpaper paths matching the given pattern(s).
    Doesn't clear duplicates (use a set).
    """
    for pattern in patterns:
        pattern = os.path.expanduser(pattern)
        for path in glob(pattern):
            if os.path.isfile(path):
                yield os.path.realpath(path)
            else:
                yield from images_in_dir(path)

def images_in_dir(root_dir):
    """Helper function to get a list of all wallpapers in a directory"""
    for directory, _, files in os.walk(root_dir):
        for f in files:
            yield os.path.realpath(os.path.join(directory, f))


# Some combinations of transformations can be simplified
_simple_trans = {
    # (flip_horizontal, flip_vertical, rotate)
    (True, True, 0):     (False, False, 180),
    (True, True, 90):    (False, False, 270),
    (False, True, 180):  (True, False, 0),
    (True, False, 180):  (False, True, 0),
    (True, True, 180):   (False, False, 0),
    (True, True, 270):   (False, False, 90),
}

class Wallpaper(Observable):
    """Model representing one wallpaper"""

    @property
    def path(self):
        try:
            return self.paths[0]
        except IndexError:
            return None

    @property
    def width(self):
        return self._height if self.transformations[2] % 180 else self._width

    @property
    def height(self):
        return self._width if self.transformations[2] % 180 else self._height

    @property
    def has_transformations(self):
        return (self.x_offset or self.y_offset or self.zoom != 1 or
                any(self.transformations))

    __slots__ = ('hash', 'int_hash', 'paths', 'invalid_paths',
                 'format', '_width', '_height',
                 'added', 'modified',
                 '_rating', '_purity', '_tags',
                 '_x_offset', '_y_offset', '_zoom', '_transformations')

    rating = observed_property("rating", 0)
    purity = observed_property("purity", 0)
    tags = observed_property("tags", ())
    x_offset = observed_property("x_offset", 0)
    y_offset = observed_property("y_offset", 0)
    zoom = observed_property("zoom", 1)
    transformations = observed_property("transformations", (False, False, 0))

    def rotate(self, degree):
        hori, vert, rot = self.transformations
        new_trafos = hori, vert, (rot + degree) % 360
        self.transformations = _simple_trans.get(new_trafos, new_trafos)

    def flip_vertical(self):
        hori, vert, rot = self.transformations
        new_trafos = hori, not vert, rot
        self.transformations = _simple_trans.get(new_trafos, new_trafos)

    def flip_horizontal(self):
        hori, vert, rot = self.transformations
        new_trafos = not hori, vert, rot
        self.transformations = _simple_trans.get(new_trafos, new_trafos)

    def __init__(self, hash, paths, format, width, height, added, modified,
                 invalid_paths=None, **props):
        super().__init__()
        self.hash = hash
        self.int_hash = builtins.hash(int(hash, 16)) # truncated int
        self.paths = paths
        self.format = format
        self._width = width
        self._height = height
        self.added = added
        self.modified = modified
        self.invalid_paths = invalid_paths or []
        for attr, value in props.items():
            setattr(self, "_" + attr, value)
        self.subscribe(self)

    def notify(self, *_):
        self.modified = datetime.now()

    def __repr__(self):
        return self.__class__.__name__ + ":" + self.hash

    def __eq__(self, other):
        if isinstance(other, Wallpaper):
            return self.int_hash == other.int_hash
        return NotImplemented

    def __hash__(self):
        return self.int_hash

    def to_json(self):
        """Dictionary representation of this object for storing.
        Excludes path so it can be used as key.
        """
        # simple attributes, always present
        data = {
            'paths': self.paths,
            'format': self.format,
            'width': self._width,
            'height': self._height,
            'added': self.added,
            'modified': self.modified,
        }
        # attributes with common defaults may not need to be stored
        for attr in ('rating', 'purity',
                     'x_offset', 'y_offset', 'zoom',
                     'rotate', 'flip_vertical', 'flip_horizontal'):
            try:
                data[attr] = getattr(self, "_" + attr)
            except AttributeError:
                pass
        # attributes that are mutable iterables
        for attr in 'tags', 'invalid_paths':
            value = getattr(self, attr)
            if value:
                data[attr] = value
        return data

    def open(self):
        subprocess.Popen(args=("/usr/bin/eog", self.path))

    @tags.setter
    @observed
    def tags(self, tags):
        if isinstance(tags, str):
            tags = map(str.strip, tags.split(","))
        self._tags = tuple(sorted(set(filter(None, tags))))

    def check_paths(self):
        for path in self.paths:
            if not os.path.isfile(path):
                self._invalidate_path(path, "File does not exist.")
            elif not os.access(path, os.R_OK):
                self._invalidate_path(path, "No permission to read file.")
        if not self.paths:
            log.warning("No valid paths left for wallpaper '%s'", self.hash)
            return False
        return True

    @observed
    def _invalidate_path(self, path, reason):
        self.paths.remove(path)
        if path not in self.invalid_paths:
            self.invalid_paths.append(path)
        log.warning("Invalidated wallpaper path '%s' (%s remaining)."
                    "Reason: %s",
                    path, len(self.paths), reason)

    def transformed(self, screen_width=1920, screen_height=1080):
        if not self.has_transformations:
            return self.path
        unique_hash = hash((self, self.x_offset, self.y_offset, self.zoom,
                            self.transformations))
        path = "/tmp/walliser_{:x}.jpg".format(unique_hash)
        if os.path.isfile(path):
            log.debug("Found transformed '%s'", path)
            return path
        with Image.open(self.path) as img:
            log.debug("Creating transformed '%s'", path)
            horizontal, vertical, rotate = self.transformations
            if horizontal:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            if vertical:
                img = img.transpose(Image.FLIP_TOP_BOTTOM)
            if rotate:
                img = img.rotate(rotate, expand=True)
            scale = self.zoom * max(screen_width / img.width,
                                    screen_height / img.height)
            if scale != 1:
                img = img.resize((int(img.width * scale),
                                  int(img.height * scale)),
                                 resample=Image.LANCZOS)
            left = (img.width - screen_width) / 2 + self.x_offset
            top = (img.height - screen_height) / 2 + self.y_offset
            img = img.crop((left, top, left + screen_width,
                                       top + screen_height))
            img.save(path)
        return path


def make_query(expression):
    """Turn an expression into a function, assigning Wallpaper properties to
    (possibly abbreviated) variable names as needed. Unknown names are
    interpreted as tags."""
    attributes = ("rating", "purity", "tags",
                  "width", "height", "format",
                  "added", "modified",
                  "x_offset", "y_offset", "zoom", "transformations")
    builtins = {"min": min, "max": max, "sum": sum, "map": map,
                "int": int, "bool": bool, "str": str, "repr": repr,
                "parse_relative_time": parse_relative_time}
    keywords = set(builtins) | {"and", "or", "not", "lambda",
                                "if", "then", "else", "for", "in",
                                "True", "False", "None"}
    def replacer(match):
        """Replace abbreviated attributes and tags."""
        word = match.group(0)
        if word in keywords:
            return word
        for attr in attributes:
            if attr.startswith(word):
                return "wp." + attr
        if re.fullmatch(r"(:?\d+[sMHdwmy])+", word):
            return f"parse_relative_time('{word[1:]}')"
        return f"('{word}' in wp.tags)"

    expression = re.sub(r"[A-Za-z][A-Za-z0-9_]*", replacer, expression)
    definition = "lambda wp: bool({})".format(expression)
    try:
        # Let's hope this is safe. Mainly guard against accidents.
        query = eval(definition, {"__builtins__": builtins})
    except SyntaxError:
        raise SyntaxError("Invalid query expression `{}`.".format(expression)) from None
    return query, expression


class WallpaperController:
    """Manages a collection of relevant wallpapers and takes care of some
    config related IO (TODO: isolate the IO)."""

    def __init__(self, config, sources=None, query="True", sort=False):
        self._config = config
        self._updated_wallpapers = set()
        self._updates_saved = 0

        self.wallpapers = []

        try:
            config_data = config["wallpapers"]
        except (TypeError, KeyError):
            config_data = {}

        query, query_expression = make_query(query)
        log.debug("Using query `%s`", query_expression)

        if sources:
            wallpapers = self.wallpapers_from_paths(sources, config_data)
        else:
            wallpapers = (Wallpaper(hash=hash, **data)
                          for hash, data in config_data.items()
                          if data['paths'])

        self.wallpapers = []
        for wp in set(filter(query, wallpapers)):
            wp.subscribe(self)
            self.wallpapers.append(wp)

        if self._updated_wallpapers:
            log.info("Found %d new wallpapers.", len(self._updated_wallpapers))

        if not self.wallpapers:
            raise Exception('No matching wallpapers found. Query: "' + query_expression + '"')
        else:
            log.debug("Found %d matching wallpapers.", len(self.wallpapers))

        if sort:
            self.wallpapers.sort(key=attrgetter("path"))
        else:
            shuffle(self.wallpapers)

    def wallpapers_from_paths(self, sources, config_data={}):
        """Iterate wallpapers in given paths, including new ones."""
        known_paths = {path: hash for hash, data in config_data.items()
                                    for path in data["paths"] }
        now = datetime.now()
        images = set(progress(find_images(sources)))
        for path in progress(images):
            if path in known_paths:
                hash = known_paths[path]
                data = config_data[hash]
                # check for outdated data formatting
                updated = False
                if "added" not in data:
                    updated = True
                    data["added"] = data["modified"] = now
            else: # new path
                updated = True
                try:
                    img = Image.open(path) # Do this first to abort immediately
                                           # for non-images.
                    hash = get_file_hash(path)
                    if hash in config_data:
                        log.debug("Adding path of know wallpaper '%s'", path)
                        data = config_data[hash].copy()
                        data["paths"].append(path)
                        data["paths"].sort()
                    else:  # new file
                        log.debug("Added new wallpaper '%s'", path)
                        data = {
                            "paths": [path],
                            "format": img.format,
                            "width": img.size[0],
                            "height": img.size[1],
                            "added": now,
                            "modified": now,
                        }
                except IOError:
                    log.warning("Can't open '%s'", path)
                    continue
            wp = Wallpaper(hash=hash, **data)
            if updated:
                self._updated_wallpapers.add(wp)
            yield wp

    def notify(self, wallpaper, *_):
        self._updated_wallpapers.add(wallpaper)

    def save_updates(self):
        if not self._updated_wallpapers:
            return
        updates_count = len(self._updated_wallpapers)
        self._config["wallpapers"].update((wp.hash, wp.to_json())
                                         for wp in self._updated_wallpapers)
        self._config.save()
        self._updated_wallpapers = set()
        self._updates_saved += updates_count
        log.info("%d update%s %ssaved (%d total)",
                 updates_count,
                 "" if updates_count == 1 else "s",
                 "NOT " if self._config.readonly else "",
                 self._updates_saved)
