# -*- coding: utf-8 -*-

import os
import subprocess
import builtins
import logging
from collections import namedtuple
from operator import attrgetter
import random
from glob import iglob as glob
import re
from datetime import datetime

from PIL import Image

from .util import get_file_hash, parse_relative_time

from .database import Model, Column, Observable

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


class Transformation(namedtuple("Transformation",
        "horizontal vertical rotate zoom x_offset y_offset")):

    @property
    def is_noop(self):
        return self == Transformation.noop

    # Some combinations of transformations can be simplified
    _simplify = {
        # (horizontal, vertical, rotate)
        (True, True, 0): (False, False, 180),
        (True, True, 90): (False, False, 270),
        (False, True, 180): (True, False, 0),
        (True, False, 180): (False, True, 0),
        (True, True, 180): (False, False, 0),
        (True, True, 270): (False, False, 90),
    }

    def __post_init__(self):
        try:
            hvr = self._simplify[self[:3]]
        except KeyError:
            pass
        else:
            return self.__class__(*hvr, self[3:])

    def __repr__(self):
        return "Transform(" + ",".join(map(str, self)) + ")"

    def rotate_by(self, degree):
        return self.__class__(self.horizontal, self.vertical,
                              (self.rotate + degree) % 360,
                              *self[3:])

    def flip_vertical(self):
        return self.__class__(self.horizontal, not self.vertical, *self[2:])

    def flip_horizontal(self):
        return self.__class__(not self.horizontal, *self[1:])

    def zoom_by(self, factor):
        return self.zoom_to(self.zoom + factor)

    def zoom_to(self, zoom):
        return self.__class__(*self[:3], zoom, *self[4:])

    def shift(self, x=0, y=0):
        return self.__class__(*self[:4], self.x_offset + x, self.y_offset + y)

    def _sqlite_adapt_(self):
        parts = int(self.horizontal), int(self.vertical), *self[2:]
        return ";".join(map(str, parts)).encode('ascii')

    @classmethod
    def _sqlite_convert_(cls, bytestring):
        hor, vert, *parts = bytestring.split(b";")
        hor, vert = hor == "1", vert == "1"
        converted = (t(p) for t, p in zip((int, float, int, int), parts))
        return Transformation(hor, vert, *converted)

Transformation.noop = Transformation(False, False, 0, 1, 0, 0)


class Wallpaper(Model, Observable):
    """Model representing one wallpaper"""

    _tablename_ = "wallpaper"

    hash = Column("TEXT", mutable=False, nullable=False)
    format = Column("INTEGER", mutable=False, nullable=False)
    height = Column("INTEGER", mutable=False, nullable=False)
    width = Column("INTEGER", mutable=False, nullable=False)

    added = Column("TIMESTAMP", mutable=False, nullable=False)
    modified = Column("TIMESTAMP", default=datetime.min, observed=False)

    rating = Column("INTEGER", default=0)
    purity = Column("INTEGER", default=0)
    views = Column("INTEGER", default=0, observed=False)

    transformation = Column(Transformation, default=Transformation.noop)

    paths = Column("TUPLE", default=())
    invalid_paths = Column("FROZENSET", default=frozenset(), observed=False)
    tags = Column("FROZENSET", default=frozenset())

    @property
    def path(self):
        try:
            return self.paths[0]
        except IndexError:
            return None

    @property
    def mtime(self):
        return os.path.getmtime(self.path)

    @property
    def transformed_width(self):
        # TODO apply zoom?
        return self.height if self.transformation.rotate % 180 else self.width

    @property
    def transformed_height(self):
        # TODO apply zoom?
        return self.width if self.transformation.rotate % 180 else self.height

    def __repr__(self):
        return (self.__class__.__name__
                + ":" + self.hash
                + ":Tags{" + ",".join(self.tags) + "}"
                + ":" + repr(self.transformation)
                )

    def __eq__(self, other):
        if isinstance(other, Wallpaper):
            return hash(self) == hash(other)
        return NotImplemented

    def __hash__(self):
        return hash(int(self.hash, 16))

    def increment_views(self):
        """Idempotent for this session"""
        if hasattr(self, '_views_incremented'):
            return
        self._views_incremented = True
        self.views += 1

    def open(self):
        # subprocess.Popen(args=("/usr/bin/eog", self.path))
        subprocess.Popen(args=("feh", "--fullscreen", self.path))

    def set_tags(self, csv):
        """Set tags via comma separated string."""
        self.tags = {tag.strip() for tag in csv.split(",")}

    def rotate_by(self, degree):
        self.transformation = self.transformation.rotate_by(degree)

    def flip_vertical(self):
        self.transformation = self.transformation.flip_vertical(degree)

    def flip_horizontal(self):
        self.transformation = self.transformation.flip_horizontal(degree)

    def zoom_by(self, factor):
        self.transformation = self.transformation.zoom_by(factor)

    def zoom_to(self, zoom):
        self.transformation = self.transformation.zoom_to(zoom)

    def shift(self, x=0, y=0):
        self.transformation = self.transformation.shift(x, y)

    def clear_transformation(self):
        self.transformation = Transformation.noop

    def check_paths(self):
        remaining, invalid = [], []
        for path in self.paths:
            if os.path.isfile(path):
                remaining.append(path)
                if not os.access(path, os.R_OK):
                    log.warning("No permission to read file '%s'", path)
            else:
                invalid_paths.append(path)
        self.paths = tuple(remaining)
        self.invalid_paths = frozenset(invalid)
        if not remaining:
            log.warning("No valid paths left for wallpaper '%s'", self.hash)
            return False
        return True

    def transformed(self, screen_width=1920, screen_height=1080):
        # TODO maybe turn into Transformation.apply
        if self.transformation.is_noop:
            return self.path
        unique_hash = hash((self, self.transformation))
        path = "/tmp/walliser_{:x}.{:s}".format(unique_hash,
                                    'jpg' if self.format == 'JPEG' else 'png')
        if os.path.isfile(path):
            log.debug("Found transformed '%s'", path)
            return path
        with Image.open(self.path) as img:
            log.debug("Creating transformed '%s'", path)
            if self.transformation.horizontal:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            if self.transformation.vertical:
                img = img.transpose(Image.FLIP_TOP_BOTTOM)
            if self.transformation.rotate:
                img = img.rotate(self.transformation.rotate, expand=True)
            scale = self.transformation.zoom * max(screen_width / img.width,
                                                   screen_height / img.height)
            if scale != 1:
                img = img.resize((int(img.width * scale),
                                  int(img.height * scale)),
                                 resample=Image.LANCZOS)
            left = (img.width - screen_width) / 2 + self.transformation.x_offset
            top = (img.height - screen_height) / 2 + self.transformation.y_offset
            img = img.crop((left, top, left + screen_width,
                                       top + screen_height))
            img.save(path)
        return path


def make_query(expression):
    """Turn an expression into a function, assigning Wallpaper properties to
    (possibly abbreviated) variable names as needed. Unknown names are
    interpreted as tags."""
    raise NotImplemented

    attributes = ("views", "rating", "purity", "tags",
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
        if re.fullmatch(r"t(:?\d+[sMHdwmy])+", word):
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

    def __init__(self, config, sources=None, query="True", sort=None, reverse=False):
        # self._config = config
        # self._updated_wallpapers = set()
        # self._updates_saved = 0

        # try:
        #     config_data = config["wallpapers"]
        # except (TypeError, KeyError):
        #     config_data = {}

        # query, query_expression = make_query(query)
        # log.debug("Using query `%s`", query_expression)

        # if sources:
        #     wallpapers = self.wallpapers_from_paths(sources, config_data)
        # else:
        #     wallpapers = (Wallpaper(hash=hash, **data)
        #                   for hash, data in config_data.items()
        #                   if data['paths'])

        self.wallpapers = list(Wallpaper.get())
        # for wp in set(filter(query, wallpapers)):
        for wp in self.wallpapers:
            wp.subscribe(self)

        # if self._updated_wallpapers:
        #     log.info("Found %d new wallpapers.", len(self._updated_wallpapers))

        if not self.wallpapers:
            query_expression = str(NotImplemented)
            raise ValueError('No matching wallpapers found. Query: "' + query_expression + '"')
        else:
            log.debug("Found %d matching wallpapers.", len(self.wallpapers))

        if sort:
            log.debug(f"sorting by {sort}")
            self.wallpapers.sort(key=attrgetter(sort), reverse=reverse)
        else:
            random.shuffle(self.wallpapers)

    def wallpapers_from_paths(self, sources, config_data={}):
        """Iterate wallpapers in given paths, including new ones."""
        raise NotImplemented
        known_paths = {path: hash for hash, data in config_data.items()
                                    for path in data["paths"] }
        now = datetime.now()
        for path in progress(set(find_images(sources))):
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
        ...
        # self._updated_wallpapers.add(wallpaper)

    def save_updates(self):
        raise NotImplemented
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
