# -*- coding: utf-8 -*-

import os
import subprocess
import builtins
from operator import attrgetter
from random import shuffle
from urllib.parse import quote as urlquote
from glob import iglob as glob
from datetime import datetime

from PIL import Image

from .util import Observable, observed, get_file_hash, info, warning, die

def set_wallpapers(*wallpaper_paths):
    """Low level wallpaper setter using feh"""
    subprocess.call(["feh", "--bg-fill", "--no-fehbg"] + list(wallpaper_paths))


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

    def __init__(self, hash, paths, format, width, height, rating, purity,
                 added, modified):
        Observable.__init__(self)
        self.hash = hash
        self.int_hash = builtins.hash(int(hash, 16)) # truncated int
        self.paths = paths
        self.format = format
        self.width = width
        self.height = height
        self._rating = rating
        self._purity = purity
        self.added = datetime.strptime(added, self.TIME_FORMAT)
        self.modified = datetime.strptime(modified, self.TIME_FORMAT)

    def __repr__(self):
        return self.path

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
            # "hash": self.hash
            "paths": self.paths,
            "format": self.format,
            "width": self.width,
            "height": self.height,
            "rating": self.rating,
            "purity": self.purity,
            "added": self.added.strftime(self.TIME_FORMAT),
            "modified": self.modified.strftime(self.TIME_FORMAT),
        }

    def matches(self, query):
        return query is None or query(
            self.rating, self.purity, self.width, self.height, self.format,
            self.rating, self.purity, self.width, self.height, self.format,
        )


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

        query = None
        if args.query:
            query = eval(
                "lambda rating,purity,width,height,format,r,p,w,h,f:"
                        + args.query,
                {"__builtins__": {"min": min, "max": max}},
                dict(),
            )

        if args.wallpaper_sources:
            wallpapers = self.wallpapers_from_paths(args.wallpaper_sources,
                                                    config_data)
        else:
            wallpapers = (Wallpaper(hash=hash, **data)
                                for hash, data in config_data.items())

        self.wallpapers = []
        for wp in set(wp for wp in wallpapers if wp.matches(query)):
            wp.subscribe(self)
            self.wallpapers.append(wp)

        if self.updated_wallpapers:
            info("Found {} new wallpapers.".format(len(self.updated_wallpapers)))

        if not self.wallpapers:
            # raise Exception("No wallpapers found.")
            die("No wallpapers found.")

        self.wallpaper_count = len(self.wallpapers)
        ui.update_wallpaper_count(self.wallpaper_count)

        if args.shuffle:
            shuffle(self.wallpapers)
        else:
            self.wallpapers.sort(key=attrgetter("path"))

    def wallpapers_from_paths(self, sources, config_data={}):
        """Iterate wallpapers in given paths, including new ones."""
        known_paths = {path: hash for hash, data in config_data.items()
                                    for path in data["paths"] }
        now = datetime.now().strftime(Wallpaper.TIME_FORMAT)
        for path in find_images(sources):
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
                            "rating": 0,
                            "purity": 0,
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

    @staticmethod
    def update_live_wallpapers(wallpapers):
        """Set actually visible wallpapers."""
        set_wallpapers(*(wp.path for wp in wallpapers))
