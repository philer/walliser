# -*- coding: utf-8 -*-

import os
import subprocess
import builtins
import logging
from operator import attrgetter
from random import shuffle
from collections import namedtuple
from glob import iglob as glob
import re
from datetime import datetime

from PIL import Image

from .util import Observable, observed, get_file_hash, parse_relative_time
from .progress import progress


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


Transform = namedtuple("Transform",
    "flip_vertical flip_horizontal rotate x_offset y_offset scale")


class Wallpaper(Observable):
    """Model representing one wallpaper"""

    TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

    @property
    def path(self):
        try:
            return self.paths[0]
        except IndexError:
            return None
            # raise AttributeError("No valid path left for " + repr(self)) from None

    # @property
    # def url(self):
    #     return "file://" + urlquote(self.path)

    @property
    def rating(self):
        return self._rating

    @rating.setter
    @observed
    def rating(self, rating):
        self._rating = rating

    @property
    def purity(self):
        return self._purity

    @purity.setter
    @observed
    def purity(self, purity):
        self._purity = purity

    @property
    def x_offset(self):
        return self._x_offset

    @x_offset.setter
    @observed
    def x_offset(self, x_offset):
        self._x_offset = x_offset

    @property
    def y_offset(self):
        return self._y_offset

    @y_offset.setter
    @observed
    def y_offset(self, y_offset):
        self._y_offset = y_offset

    @property
    def zoom(self):
        return self._zoom

    @zoom.setter
    @observed
    def zoom(self, zoom):
        self._zoom = zoom

    __slots__ = ('hash', 'int_hash', 'paths', 'invalid_paths',
                 'format', 'width', 'height',
                 'added', 'modified',
                 '_rating', '_purity', 'tags',
                 '_x_offset', '_y_offset', '_zoom'
                )
    _default_values = {
        "rating": 0,
        "purity": 0,
        "x_offset": 0,
        "y_offset": 0,
        "zoom": 1,
    }
    def __init__(self, hash, paths, format, width, height, added, modified,
                 invalid_paths=None, tags=None, **props):
        super().__init__()
        self.hash = hash
        self.int_hash = builtins.hash(int(hash, 16)) # truncated int
        self.paths = paths
        self.format = format
        self.width = width
        self.height = height
        self.added = datetime.strptime(added, self.TIME_FORMAT)
        self.modified = datetime.strptime(modified, self.TIME_FORMAT)
        self.invalid_paths = invalid_paths or []
        self.tags = tags or []
        for attr, default in self._default_values.items():
            setattr(self, "_" + attr, props.get(attr, default))

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
        data = {
            'paths': self.paths,
            'format': self.format,
            'width': self.width,
            'height': self.height,
            'added': self.added.strftime(self.TIME_FORMAT),
            'modified': self.modified.strftime(self.TIME_FORMAT),
        }
        for attr, default in self._default_values.items():
            value = getattr(self, "_" + attr)
            if value != default:
                data[attr] = value
        for attr in 'tags', 'invalid_paths':
            value = getattr(self, attr)
            if value:
                data[attr] = value
        return data

    def open(self):
        subprocess.Popen(args=("/usr/bin/eog", self.path))

    @observed
    def toggle_tag(self, tag):
        try:
            self.tags.remove(tag)
        except ValueError:
            self.tags.append(tag)
            self.tags.sort()

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
        if self.x_offset or self.y_offset or self.zoom != 1:
            scale = self.zoom * max(screen_width / self.width,
                                    screen_height / self.height)
            path = "/tmp/walliser_{:x}.jpg".format(hash(self)
                                      ^ hash(self.x_offset)
                                      ^ hash(self.y_offset)
                                      ^ hash(scale))
            if os.path.isfile(path):
                log.debug("Found cropped '%s'", path)
                return path
            with Image.open(self.path) as img:
                log.debug("Creating cropped '%s'", path)
                if scale != 1:
                    img = img.resize((int(self.width * scale),
                                      int(self.height * scale)),
                                     resample=Image.LANCZOS)
                left = (img.width - screen_width) / 2 + self.x_offset
                top = (img.height - screen_height) / 2 + self.y_offset
                img = img.crop((left, top, left + screen_width,
                                           top + screen_height))
                img.save(path)
            return path
        log.debug("Using raw path '%s'", self.path)
        return self.path


def make_query(expression):
    """Turn an expression into a function, assigning Wallpaper properties to
    (possibly abbreviated) variable names as needed. Unknown names are
    interpreted as tags."""
    attributes = ("rating", "purity", "tags",
                  "width", "height", "format",
                  "added", "modified",
                  "x_offset", "y_offset", "zoom")
    builtins = {"min": min, "max": max, "sum": sum, "map": map,
                "int": int, "bool": bool, "str": str, "repr": repr,
                "parse_relative_time": parse_relative_time}
    keywords = set(builtins) | {"and", "or", "not", "for", "in", "if", "lambda",
                                "True", "False", "None"}
    time_pattern = re.compile(r"t(:?\d+[sMHdwmy])+")
    def replacer(match):
        """Replace abbreviated attributes and tags."""
        word = match.group(0)
        if word in keywords:
            return word
        for attr in attributes:
            if attr.startswith(word):
                return "wp." + attr
        if time_pattern.fullmatch(word):
            return "parse_relative_time('{}')".format(word[1:])
        return "('{}' in wp.tags)".format(word)

    expression = re.sub(r"[A-Za-z_][A-Za-z0-9_]*", replacer, expression)
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
        self.config = config
        self.stats = {"saved_updates": 0}

        self.wallpapers = []
        self.updated_wallpapers = set()

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

        if self.updated_wallpapers:
            log.info("Found %d new wallpapers.", len(self.updated_wallpapers))

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
        now = datetime.now().strftime(Wallpaper.TIME_FORMAT)
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
                self.updated_wallpapers.add(wp)
            yield wp

    def notify(self, wallpaper, *_):
        self.updated_wallpapers.add(wallpaper)

    def save_updates(self):
        if not self.updated_wallpapers:
            return
        updates = dict()
        now = datetime.now()
        for wp in self.updated_wallpapers:
            wp.modified = now
            updates[wp.hash] = wp.to_json()

        self.config["wallpapers"].update(updates)
        self.config.save()

        self.updated_wallpapers = set()

        updates_count = len(updates)
        self.stats["saved_updates"] += updates_count
        log.info("%d update%s %ssaved (%d total)",
                 updates_count,
                 "" if updates_count == 1 else "s",
                 "NOT " if self.config.readonly else "",
                 self.stats["saved_updates"])
