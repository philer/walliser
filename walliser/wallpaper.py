# -*- coding: utf-8 -*-

import os
import subprocess

from collections import namedtuple
from operator import attrgetter
from random import shuffle
from urllib.parse import quote as urlquote


from PIL import Image

from glob import iglob as glob
import gzip
import codecs
import json

from .util import Observable, observed, dict_update_recursive


def set_wallpapers(*wallpaper_paths):
    """Low level wallpaper setter using feh"""
    subprocess.call(["feh", "--bg-fill", "--no-fehbg"] + list(wallpaper_paths))


ImageData = namedtuple("ImageData", [
    "path",
    "width",
    "height",
    "format",
    "rating",
    "purity",
])


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
        # (self.path, self.width, self.height, self.format) = filedata

    def __repr__(self):
        return self.path

    def __eq__(self, other):
        return self.path == other.path

    def __hash__(self, other):
        return hash(Wallpaper) ^ hash(self.path)


class WallpaperController:
    """Manages a collection of relevant wallpapers and takes care of some
    config related IO (TODO: isolate the IO)."""

    KNOWN_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif"]

    def __init__(self, ui, args):
        self.args = args

        data = dict()
        if args.config_file:
            config = self.load_config(args.config_file, {"wallpapers":[]})
            data = config["wallpapers"]

        paths = []
        if args.wallpaper_sources:
            paths = self.find_images(args.wallpaper_sources)

        query = None
        allow_defaults = True
        if args.query:
            query = eval(
                "lambda r,p: " + args.query,
                {"__builtins__": {"min", min, "max", max}},
                dict(),
            )
            allow_defaults = query(0, 0)
            def query_test(data):
                return query(data.rating, data.purity)

        args_data = []
        # Try to optimize the expensive filtering as much as possible.
        if data and paths:
            if query:
                if allow_defaults:
                    # all paths with data that matches
                    args_data = filter(query_test,
                        self.image_data(paths, data))
                else:
                    # all paths from data that were requested and match
                    args_data = (ImageData(path=path, **args)
                        for path, args in data.items())
                    paths = set(paths)
                    args_data = (args for args in args_data
                        if query_test(args) and args.path in paths)
            else:
                # all paths with data
                args_data = self.image_data(paths, data)


        elif data and not paths:
            # all paths from data (that match)
            args_data = (ImageData(path=path, **args)
                for path, args in data.items())
            if query:
                args_data = filter(query_test, args_data)

        elif not data and paths and allow_defaults:
            # all paths with data
            args_data = self.image_data(paths)

        self.wallpapers = [Wallpaper(*args) for args in args_data]
        if not self.wallpapers:
            raise Exception("No wallpapers found.")

        if args.wallpaper_sources and args.config_file:
            self.store_config(args.config_file, config)

        self.wallpaper_count = len(self.wallpapers)
        ui.update_wallpaper_count(self.wallpaper_count)

        if args.shuffle:
            shuffle(self.wallpapers)
        else:
            self.wallpapers.sort(key=attrgetter("path"))


    def find_images(self, patterns):
        """Returns an iterable of wallpaper paths matching the given pattern(s).
        Doesn't clear duplicates (use a set).
        """
        for pattern in patterns:
            pattern = os.path.expanduser(pattern)
            for path in glob(pattern):
                if os.path.isfile(path):
                    yield os.path.realpath(path)
                else:
                    yield from self.images_in_dir(path)

    def images_in_dir(self, root_dir):
        """Helper function to get a list of all wallpapers in a directory"""
        for directory, _, files in os.walk(root_dir):
            for f in files:
                yield os.path.realpath(os.path.join(directory, f))

    def image_data(self, path, known_data=dict()):
        """Retrieve image information by checking real file (headers).
        This works for single paths (string -> ImageData)
        and for iterables (iterable<string> -> iterable<ImageData>).
        """
        if not isinstance(path, str):
            # return filter(None, map(self.image_data, path, known_data))
            return filter(None, (self.image_data(p, known_data) for p in path))

        try:
            return ImageData(path=path, **known_data[path])
        except KeyError:
            try:
                img = Image.open(path)
            except IOError:
                return None
            else:
                return ImageData(
                    path=path,
                    width=img.size[0],
                    height=img.size[1],
                    format=img.format,
                    rating=0,
                    purity=0,
                )

    # def is_image_file(self, path):
    #     """Rudimentary check for know filename extensions, no magic."""
    #     return path[path.rfind("."):].lower() in self.KNOWN_EXTENSIONS

    def load_config(self, filename, default=None):
        """Load data from config file.
        If file is empty or doesn't exist returns default or raises exception.
        """
        try:
            with self.open_config_file(filename, "r") as config_file:
                return json.load(config_file)
        except FileNotFoundError:
            if default is not None:
                return default
            raise
        except ValueError:
            # only raise if the file was not empty (really "malformed")
            if os.stat(filename).st_size and default is not None:
                return default
            raise

    def store_config(self, filename, config=dict(), pretty="auto"):
        """Save current configuration into given file."""
        config = config or self.load_config(filename)
        dict_update_recursive(config, {
            "wallpapers": {wp.path: wp.as_dict for wp in self.wallpapers}
        })
        with self.open_config_file(self.args.config_file, "w") as config_file:
            if pretty == True or pretty == "auto" and filename[-3:] != ".gz":
                json.dump(config, config_file,
                    sort_keys=True, indent="\t")
            else:
                json.dump(config, config_file,
                    sort_keys=False, separators=(",", ":"))

    def open_config_file(self, filename, mode="r"):
        """Open a I/O of JSON data, respecting .gz file endings."""
        if filename[-3:] == ".gz":
            return gzip.open(filename, mode + "t", encoding="UTF-8")
        else:
            return codecs.open(filename, mode, encoding="UTF-8")


    def update_live_wallpapers(self, wallpapers):
        """Set actually visible wallpapers."""
        set_wallpapers(*(wp.path for wp in wallpapers))
