# -*- coding: utf-8 -*-

import os
import subprocess
import builtins
from operator import attrgetter
from random import shuffle
from urllib.parse import quote as urlquote
from glob import iglob as glob
from re import sub
from datetime import datetime

from PIL import Image

from .util import (Observable, observed,
                   get_file_hash,
                   info, warning, die,
                   progress_spinner, progress_bar)

def set_wallpaper_paths(wallpaper_paths):
    """Low level wallpaper setter using feh"""
    subprocess.call(["feh", "--bg-fill", "--no-fehbg"] + list(wallpaper_paths))

live_wallpapers = []

def show_wallpapers(wallpapers):
    """Set actually visible wallpapers."""
    global live_wallpapers
    live_wallpapers = list(wallpapers)
    set_wallpaper_paths((wp.path for wp in live_wallpapers))

def show_wallpaper(screen_index, wallpaper):
    """Set actually visible wallpapers."""
    live_wallpapers[screen_index] = wallpaper
    set_wallpaper_paths((wp.path for wp in live_wallpapers))


def find_images(patterns):
    """Returns an iterable of wallpaper paths matching the given pattern(s).
    Doesn't clear duplicates (use a set).
    """
    spinner = progress_spinner()
    for pattern in patterns:
        pattern = os.path.expanduser(pattern)
        for path in glob(pattern):
            if os.path.isfile(path):
                spinner(path)
                yield os.path.realpath(path)
            else:
                for directory, _, files in os.walk(path):
                    for f in files:
                        img_path = os.path.realpath(os.path.join(directory, f))
                        spinner(img_path)
                        yield img_path


class Wallpaper(Observable):
    """Model representing one wallpaper"""

    TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

    @property
    def path(self):
        return self.paths[0] # TODO check for existance

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

    def __init__(self, hash, paths, format, width, height, added, modified,
                 rating=0, purity=0, tags=None):
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
        self.tags = set(tags) if tags else set()

    def __repr__(self):
        return self.__class__.__name__ + ":" + self.path

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
        return {
            "paths": self.paths,
            "format": self.format,
            "width": self.width,
            "height": self.height,
            "added": self.added.strftime(self.TIME_FORMAT),
            "modified": self.modified.strftime(self.TIME_FORMAT),
            "rating": self.rating,
            "purity": self.purity,
            "tags": sorted(list(self.tags))
        }

    @observed
    def toggle_tag(self, tag):
        try:
            self._tags.remove(tag)
        except KeyError:
            self._tags.add(tag)

    def show(self, screen_index=0):
        show_wallpaper(screen_index, self)


def make_query(expression):
    attributes = ("rating", "purity", "tags",
                  "width", "height", "format",
                  "added", "modified")
    def replacer(match):
        word = match.group(0)
        for attr in attributes:
            try:
                return "_wp." + next(a for a in attributes if a.startswith(word))
            except StopIteration:
                pass
        return word
    return eval(
        "lambda _wp:" + sub("[A-Za-z]+", replacer, expression),
        {"__builtins__": {"min": min, "max": max}},
        {})


class WallpaperController:
    """Manages a collection of relevant wallpapers and takes care of some
    config related IO (TODO: isolate the IO)."""

    def __init__(self, ui, config, args):
        self.wallpapers = []
        self.updated_wallpapers = set()

        try:
            config_data = config["wallpapers"]
        except (TypeError, KeyError):
            config_data = {}

        query = make_query(args.query or "True")

        if args.wallpaper_sources:
            wallpapers = self.wallpapers_from_paths(args.wallpaper_sources,
                                                    config_data)
        else:
            wallpapers = (Wallpaper(hash=hash, **data)
                                for hash, data in config_data.items())

        self.wallpapers = []
        for wp in set(wp for wp in wallpapers if query(wp)):
            wp.subscribe(self)
            self.wallpapers.append(wp)

        if self.updated_wallpapers:
            info("Found {} new wallpapers.".format(len(self.updated_wallpapers)))

        if not self.wallpapers:
            # raise Exception("No wallpapers found.")
            die("No wallpapers found.")

        ui.update_wallpaper_count(len(self.wallpapers))

        if args.shuffle:
            shuffle(self.wallpapers)
        else:
            self.wallpapers.sort(key=attrgetter("path"))

    def wallpapers_from_paths(self, sources, config_data={}):
        """Iterate wallpapers in given paths, including new ones."""
        known_paths = {path: hash for hash, data in config_data.items()
                                    for path in data["paths"] }
        now = datetime.now().strftime(Wallpaper.TIME_FORMAT)
        images = list(find_images(sources))
        bar = progress_bar(len(images))
        for path in images:
            bar(after_text="processing " + path)
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
                        data = config_data[hash].copy()
                        data["paths"].append(path)
                        data["paths"].sort()
                    else:  # new file
                        data = {
                            "paths": [path],
                            "format": img.format,
                            "width": img.size[0],
                            "height": img.size[1],
                            "added": now,
                            "modified": now,
                        }
                except IOError:
                    warning("Can't open 'file://{}'".format(urlquote(path)))
                    continue
            wp = Wallpaper(hash=hash, **data)
            if updated:
                self.updated_wallpapers.add(wp)
            yield wp

    def notify(self, wallpaper, *_):
        self.updated_wallpapers.add(wallpaper)

    def updated_json(self):
        now = datetime.now()
        data = dict()
        for wp in self.updated_wallpapers:
            wp.modified = now
            data[wp.hash] = wp.to_json()
        self.updated_wallpapers = set()
        return data
