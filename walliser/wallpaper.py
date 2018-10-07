# -*- coding: utf-8 -*-

import os
import subprocess
import builtins
import logging
from operator import attrgetter
from itertools import zip_longest
from random import shuffle
from urllib.parse import quote as urlquote
from glob import iglob as glob
import re
from datetime import datetime

from PIL import Image

from .util import Observable, observed, get_file_hash, parse_relative_time
from .progress import progress


log = logging.getLogger(__name__)

live_wallpaper_paths = ()

def _display_wallpapers(wallpaper_paths):
    """Low level wallpaper setter using feh"""
    args = ("feh", "--bg-fill", "--no-fehbg") + tuple(wallpaper_paths)
    try:
        subprocess.run(args=args, check=True, universal_newlines=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as cpe:
        log.warning("setting wallpapers failed '%s'", wallpaper_paths)
        log.debug(cpe.output)
        # raise
        return False
    return True

def set_wallpaper_paths(wallpaper_paths):
    wallpaper_paths = tuple(path if path else live for path, live in
                            zip_longest(wallpaper_paths, live_wallpaper_paths))
    if _display_wallpapers(wallpaper_paths):
        global live_wallpaper_paths
        live_wallpaper_paths = wallpaper_paths

def set_wallpaper_path(wallpaper_path, screen_index=0):
    set_wallpaper_paths([None] * screen_index + [wallpaper_path])

def show_wallpapers(wallpapers):
    wallpapers = tuple(wallpapers)
    for wp in wallpapers:
        wp.check_paths()
    set_wallpaper_paths(wp.path for wp in wallpapers)

def show_wallpaper(wallpaper, screen_index=0):
    wallpaper.check_paths()
    set_wallpaper_path(wallpaper.path, screen_index)


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

    @property
    def url(self):
        return "file://" + urlquote(self.path)

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

    __slots__ = ('hash', 'int_hash', 'paths', 'invalid_paths',
                 'format', 'width', 'height',
                 'added', 'modified',
                 '_rating', '_purity', 'tags',
                )
    def __init__(self, hash, paths, format, width, height, added, modified,
                 invalid_paths=None, rating=0, purity=0, tags=None):
        super().__init__()
        self.hash = hash
        self.int_hash = builtins.hash(int(hash, 16)) # truncated int
        self.paths = paths
        self.format = format
        self.width = width
        self.height = height
        self.added = datetime.strptime(added, self.TIME_FORMAT)
        self.modified = datetime.strptime(modified, self.TIME_FORMAT)
        self._rating = rating
        self._purity = purity
        self.invalid_paths = set(invalid_paths or ())
        self.tags = tags or []

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
            'rating': self.rating,
            'purity': self.purity,
        }
        for attr in 'tags', 'invalid_paths':
            value = getattr(self, attr)
            if value:
                data[attr] = value
        return data

    def check_paths(self):
        for path in self.paths:
            if not os.path.isfile(path):
                self._invalidate_path(path, "File does not exist.")
            elif not os.access(path, os.R_OK):
                self._invalidate_path(path, "No permission to read file.")
        if not self.paths:
            log.warning("No valid paths left for wallpaper '%s'", self.hash)

    @observed
    def _invalidate_path(self, path, reason):
        self.paths.remove(path)
        self.invalid_paths.add(path)
        log.warning("Invalidated wallpaper path '%s' (%s remaining). Reason: %s",
                    path, len(self.paths), reason)

    @observed
    def toggle_tag(self, tag):
        try:
            self.tags.remove(tag)
        except ValueError:
            self.tags.append(tag)
            self.tags.sort()

    def show(self, screen_index=0):
        show_wallpaper(self, screen_index)


def make_query(expression):
    """Turn an expression into a function, assigning Wallpaper properties to
    (possibly abbreviated) variable names as needed. Unknown names are
    interpreted as tags."""
    attributes = ("rating", "purity", "tags",
                  "width", "height", "format",
                  "added", "modified")
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

    def __init__(self, ui, config, sources=None, query="True", sort=False):
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

        if ui:
            ui.update_wallpaper_count(len(self.wallpapers))

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
                        log.debug("Adding path of know wallpaper file://%s", urlquote(path))
                        data = config_data[hash].copy()
                        data["paths"].append(path)
                        data["paths"].sort()
                    else:  # new file
                        log.debug("Added new wallpaper file://%s", urlquote(path))
                        data = {
                            "paths": [path],
                            "format": img.format,
                            "width": img.size[0],
                            "height": img.size[1],
                            "added": now,
                            "modified": now,
                        }
                except IOError:
                    log.warning("Can't open 'file://%s'", urlquote(path))
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
