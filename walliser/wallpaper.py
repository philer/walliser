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

    def __repr__(self):
        return "Transformation(" + ",".join(map(str, self)) + ")"

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
        return ";".join(map(str, parts))

    @classmethod
    def _sqlite_convert_(cls, bytestring):
        hor, vert, *parts = bytestring.split(b";")
        hor, vert = hor == b"1", vert == b"1"
        converted = (t(p) for t, p in zip((int, float, int, int), parts))
        return cls(hor, vert, *converted)

Transformation.noop = Transformation(False, False, 0, 1, 0, 0)


class Wallpaper(Model, Observable):
    """Model representing one wallpaper"""

    _tablename_ = "wallpaper"

    hash = Column(str, primary=True, mutable=False, nullable=False)
    format = Column(int, mutable=False, nullable=False)
    height = Column(int, mutable=False, nullable=False)
    width = Column(int, mutable=False, nullable=False)

    added = Column(datetime, mutable=False, nullable=False)
    modified = Column(datetime, default=datetime.min, observed=False)

    rating = Column(int, default=0)
    purity = Column(int, default=0)
    views = Column(int, default=0)

    transformation = Column(Transformation, default=Transformation.noop)

    paths = Column(tuple, default=())
    invalid_paths = Column(frozenset, default=frozenset(), observed=False)
    tags = Column(frozenset, default=frozenset())

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

    def _update_modified(self, *_):
        self.modified = datetime.now()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.subscribe(self._update_modified)

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
        self.tags = frozenset(tag.strip() for tag in csv.split(","))

    def rotate_by(self, degree):
        self.transformation = self.transformation.rotate_by(degree)

    def flip_vertical(self):
        self.transformation = self.transformation.flip_vertical()

    def flip_horizontal(self):
        self.transformation = self.transformation.flip_horizontal()

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
                invalid.append(path)
        self.paths = tuple(remaining)
        self.invalid_paths |= frozenset(invalid)
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


def _expand_sql_query(query):
    """Expand abbreviated names in a sql condition."""
    if query is None:
        return "1"
    columns = Wallpaper._columns_.keys()
    keywords = {"and", "or", "in", "like"}
    def replacer(match):
        """Replace abbreviated attributes and tags."""
        word = match.group(0)
        lword = word.lower()
        if lword in keywords:
            return word
        for col in columns:
            if col.startswith(lword):
                return Wallpaper._tablename_ + "." + col
        if re.fullmatch(r"t(:?\d+[sMHdwmy])+", word):
            return "'" + str(parse_relative_time(word[1:])) + "'"
        return f"{Wallpaper._tablename_}.tags LIKE '%{word}%'"
    return re.sub(r"[A-Za-z][A-Za-z0-9_]*", replacer, query)


def _find_files(sources):
    """
    Iterate wallpaper paths matching the given pattern(s).
    Doesn't clear duplicates (use a set).
    """
    for pattern in map(os.path.expanduser, sources):
        for path in glob(pattern):
            if os.path.isfile(path):
                yield os.path.realpath(path)
            else:
                for directory, _, files in os.walk(path):
                    for file in files:
                        yield os.path.realpath(os.path.join(directory, file))


class WallpaperController:
    """
    Manages a collection of relevant wallpapers and takes care of some
    config related IO (TODO: isolate the IO).
    """

    def __init__(self, sources=None, query=None, sort=None, reverse=False):
        self._updated_wallpapers = set()
        self._updates_saved = 0

        if sources:
            paths = set(_find_files(sources))
            self._add_wallpaper_paths(paths)
        if query:
            query = _expand_sql_query(query)

        wallpapers = set(Wallpaper.get(query))
        if sources:
            wallpapers = self._filter_by_paths(wallpapers, paths)

        self.wallpapers = list(wallpapers)

        if not self.wallpapers:
            raise ValueError(f"No matching wallpapers found for query '{query}'")
        else:
            log.debug("Found %d matching wallpapers.", len(self.wallpapers))

        for wp in self.wallpapers:
            wp.subscribe(self)

        if sort:
            log.debug(f"sorting by {sort}")
            self.wallpapers.sort(key=attrgetter(sort), reverse=reverse)
        else:
            random.shuffle(self.wallpapers)

    def _filter_by_paths(self, wallpapers, paths):
        paths = set(paths)
        for wp in wallpapers:
            if set(wp.paths) & paths:
                yield wp

    def _add_wallpaper_paths(self, paths):
        """Iterate wallpapers in given paths, including new ones."""
        wallpapers = {wp.hash: wp for wp in Wallpaper.get()}
        known_paths = set()
        for wp in wallpapers.values():
            known_paths.update(wp.paths)
        new_paths = paths - known_paths
        log.debug("%s known wallpapers", len(wallpapers))
        log.debug("%s known paths", len(known_paths))
        log.debug("%s supplied paths", len(paths))
        log.debug("%s new paths", len(new_paths))

        new_wallpapers = set()
        now = datetime.now()
        for path in progress(new_paths):
            try:
                img = Image.open(path)  # Do this first to abort immediately
                                        # for non-images.
                file_hash = get_file_hash(path)
                try:
                    wp = wallpapers[file_hash]
                    wp.paths = (*wp.paths, path)
                    self._updated_wallpapers.add(wp)
                except KeyError:
                    new_wallpapers.add(Wallpaper(hash=file_hash,
                                             paths=(path,),
                                             format=img.format,
                                             width=img.size[0],
                                             height=img.size[1],
                                             added=now))
            except IOError:
                log.warning("Can't open '%s'", path)
                continue
        if new_wallpapers:
            log.info(f"Added {len(new_wallpapers)} new wallpapers.")
            Wallpaper.store_many(new_wallpapers)
        self.save_updates()


    def notify(self, wallpaper, *_):
        self._updated_wallpapers.add(wallpaper)

    def save_updates(self):
        if not self._updated_wallpapers:
            return
        updates_count = len(self._updated_wallpapers)
        Wallpaper.save_many(self._updated_wallpapers)
        self._updated_wallpapers = set()
        self._updates_saved += updates_count
        log.info("%d update%s saved (%d total)",
                 updates_count,
                 "" if updates_count == 1 else "s",
                 self._updates_saved)
