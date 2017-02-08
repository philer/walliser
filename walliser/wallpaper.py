# -*- coding: utf-8 -*-

import os
import subprocess

from operator import attrgetter
from random import shuffle
from urllib.parse import quote as urlquote
from glob import iglob as glob

from PIL import Image

from .util import Observable, observed, get_file_hash

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


def image_data(path):
    """Retrieve image information by checking real file (headers).
    This works for single paths (string -> ImageData)
    and for iterables (iterable<string> -> iterable<ImageData>).
    """
    try:
        img = Image.open(path)
    except IOError:
        # print("Can't open '{}'".format(path))
        print("Can't open 'file://{}'".format(urlquote(path)))
        return None
    else:
        return dict(
            # path=path,
            width=img.size[0],
            height=img.size[1],
            format=img.format,
            hash=get_file_hash(path),
            rating=0,
            purity=0,
        )


class Wallpaper(Observable):
    """Model representing one wallpaper"""

    @property
    def as_dict(self):
        """Dictionary representation of this object for storing.
        Excludes path so it can be used as key.
        """
        return {
            "paths": self.paths,
            # "hash": self.hash,
            "format": self.format,
            "width": self.width,
            "height": self.height,
            "rating": self.rating,
            "purity": self.purity,
        }

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

    def __init__(self, paths, hash, format, width, height, rating, purity):
        Observable.__init__(self)
        self.paths = paths
        self.hash = hash
        self.format = format
        self.width = width
        self.height = height
        self.rating = rating
        self.purity = purity

    def __repr__(self):
        return self.path

    def __eq__(self, other):
        return self.hash == other.hash
        # return self.path == other.path

    def __hash__(self):
        # return hash(Wallpaper) ^ hash(self.path)
        return int(self.hash, 16)

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
                "lambda rating=0,purity=0,width=0,height=0,format='',r=0,p=0,w=0,h=0,f='':"
                    + args.query,
                {"__builtins__": {"min": min, "max": max}},
                dict(),
            )

        if args.wallpaper_sources:
            print("Searching for wallpapers.")
            # setting up a fast lookup - note that we need the hash since it's
            # not in data.
            known_paths = {path: hash for hash, data in config_data.items()
                                        for path in data["paths"] }
            print("There are {} known wallpapers in config."
                        .format(len(known_paths), config.filename))
            wallpapers = self.wallpapers_from_paths(
                            args.wallpaper_sources, known_paths, config_data, query)
        else:
            wallpapers = self.wallpapers_from_config(config_data, query)

        self.wallpapers = []
        for wp in wallpapers:
            self.wallpapers.append(wp)
            wp.subscribe(self)

        if self.updated_wallpapers:
            print("Found {} new wallpapers.".format(len(self.updated_wallpapers)))

        if not self.wallpapers:
            raise Exception("No wallpapers found.")

        self.wallpaper_count = len(self.wallpapers)
        ui.update_wallpaper_count(self.wallpaper_count)

        if args.shuffle:
            shuffle(self.wallpapers)
        else:
            self.wallpapers.sort(key=attrgetter("path"))


    def wallpapers_from_paths(self, sources, known_paths, config_data={}, query=None):
        """Iterator used when paths were specified."""
        allow_defaults = query is None or query()
        for path in find_images(sources):
            try:
                hash = known_paths[path]
            except KeyError:
                if allow_defaults:
                    data = image_data(path)
                    if data:
                        wp = Wallpaper(paths=[path], **data)
                        self.updated_wallpapers.add(wp)
                        yield wp
            else:
                data = config_data[hash]
                wp = Wallpaper(hash=hash, **data)
                if path not in wp.paths:
                    wp.paths.append(path)
                    wp.paths.sort()
                    self.updated_wallpapers.add(wp)
                if wp.matches(query):
                    yield wp

    def wallpapers_from_config(self, config_data={}, query=None):
        """Itertor used when no paths arguments were provided."""
        for hash, data in config_data.items():
            wp = Wallpaper(hash=hash, **data)
            if wp.matches(query):
                yield wp

    def notify(self, wallpaper, *_):
        self.updated_wallpapers.add(wallpaper)

    def update_config(self, config):
        if not self.updated_wallpapers:
            return 0
        entries = len(self.updated_wallpapers)
        config.rec_update({
            "wallpapers": {
                wp.hash: wp.as_dict for wp in self.updated_wallpapers
            },
        })
        self.updated_wallpapers = set()
        return entries

    @staticmethod
    def update_live_wallpapers(wallpapers):
        """Set actually visible wallpapers."""
        set_wallpapers(*(wp.path for wp in wallpapers))
