# -*- coding: utf-8 -*-

import os
import subprocess

from operator import attrgetter
from random import shuffle
from urllib.parse import quote as urlquote


from PIL import Image

from glob import iglob as glob

from .util import Observable, observed


def set_wallpapers(*wallpaper_paths):
    """Low level wallpaper setter using feh"""
    subprocess.call(["feh", "--bg-fill", "--no-fehbg"] + list(wallpaper_paths))


class Wallpaper(Observable):
    """Model representing one wallpaper"""

    @property
    def as_dict(self):
        """Dictionary representation of this object for storing.
        Excludes path so it can be used as key.
        """
        return {
            # "path": self.path,
            "width": self.width,
            "height": self.height,
            "format": self.format,
            "rating": self.rating,
            "purity": self.purity,
        }

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

    def __init__(self, path, width, height, format, rating, purity):
        Observable.__init__(self)
        self.path = path
        self.width = width
        self.height = height
        self.format = format
        self.rating = rating
        self.purity = purity

    def __repr__(self):
        return self.path

    def __eq__(self, other):
        return self.path == other.path

    def __hash__(self):
        return hash(Wallpaper) ^ hash(self.path)


class WallpaperController:
    """Manages a collection of relevant wallpapers and takes care of some
    config related IO (TODO: isolate the IO)."""

    KNOWN_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif"]

    def __init__(self, ui, config, args):
        self.wallpapers = []
        self.updated_wallpapers = set()

        try:
            config_data = config["wallpapers"]
        except (TypeError, KeyError):
            config_data = {}

        # set up the query for filtering wallpapers
        query = None
        if args.query:
            query = eval(
                "lambda r,p: " + args.query,
                {"__builtins__": {"min": min, "max": max}},
                dict(),
            )

        if args.wallpaper_sources:
            allow_defaults = query is None or query(0, 0)
            for path in self.find_images(args.wallpaper_sources):
                try:
                    data = config_data[path]
                except KeyError:
                    if allow_defaults:
                        data = self.image_data(path)
                        if data:
                            wp = Wallpaper(**data)
                            self.wallpapers.append(wp)
                            self.updated_wallpapers.add(wp)
                else:
                    if (query is None
                        or query(data["rating"], data["purity"])
                        ):
                        self.wallpapers.append(Wallpaper(path, **data))
        elif query:
            self.wallpapers = [
                Wallpaper(path, **data)
                for path, data in config_data.items()
                if query(data["rating"], data["purity"])
            ]
        else:
            self.wallpapers = [
                Wallpaper(path, **data)
                for path, data in config_data.items()
            ]

        if not self.wallpapers:
            raise Exception("No wallpapers found.")

        self.wallpaper_count = len(self.wallpapers)
        ui.update_wallpaper_count(self.wallpaper_count)

        if args.shuffle:
            shuffle(self.wallpapers)
        else:
            self.wallpapers.sort(key=attrgetter("path"))


    @classmethod
    def find_images(cls, patterns):
        """Returns an iterable of wallpaper paths matching the given pattern(s).
        Doesn't clear duplicates (use a set).
        """
        for pattern in patterns:
            pattern = os.path.expanduser(pattern)
            for path in glob(pattern):
                if os.path.isfile(path):
                    yield os.path.realpath(path)
                else:
                    yield from cls.images_in_dir(path)

    @staticmethod
    def images_in_dir(root_dir):
        """Helper function to get a list of all wallpapers in a directory"""
        for directory, _, files in os.walk(root_dir):
            for f in files:
                yield os.path.realpath(os.path.join(directory, f))


    def image_data(self, path): #, known_data=dict()
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
                path=path,
                width=img.size[0],
                height=img.size[1],
                format=img.format,
                rating=0,
                purity=0,
            )

    def updated(self, wallpaper):
        self.updated_wallpapers.add(wallpaper)

    def update_config(self, config):
        if not self.updated_wallpapers:
            return 0
        entries = len(self.updated_wallpapers)
        config.update({
            "wallpapers": {
                wp.path: wp.as_dict for wp in self.updated_wallpapers
            },
        })
        self.updated_wallpapers = set()
        return entries

    @staticmethod
    def update_live_wallpapers(wallpapers):
        """Set actually visible wallpapers."""
        set_wallpapers(*(wp.path for wp in wallpapers))
