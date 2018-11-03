# -*- coding: utf-8 -*-

import subprocess
import logging
import re

from .util import Observable, observed, steplist, modlist, each

log = logging.getLogger(__name__)

def get_screens_data():
    """Iterate data of all active screens by parsing `xrandr --query`."""
    result = subprocess.run(("xrandr", "--query"),
                            check=True, universal_newlines=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    # kinda like sscanf
    props = (('output', str), ('primary', bool), ('width', int), ('height', int))
    regex = re.compile(r"^(\S+) connected( primary)? (\d+)x(\d+)",
                       flags=re.MULTILINE | re.ASCII)
    for match in regex.findall(result.stdout):
        yield {name: type(value) for (name, type), value in zip(props, match)}


def _display_wallpapers(paths):
    """Low level wallpaper setter using feh"""
    args = ("feh", "--bg-fill", "--no-fehbg") + tuple(paths)
    try:
        subprocess.run(args=args, check=True, universal_newlines=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as cpe:
        log.warning("setting wallpapers failed '%s'", paths)
        log.debug(cpe.output)
        raise


class Collection:
    @property
    def current(self):
        try:
            return self._items[self._position]
        except IndexError:
            try:
                self.append(next(self._item_source))
            except StopIteration:
                self._position = 0
        return self._items[self._position]

    def __init__(self, item_source):
        self._item_source = item_source
        self._items = []
        self._position = -1

    def append(self, item):
        self._items.append(item)
        self._position = len(self._items) - 1

    def remove_current(self):
        self._items.pop(self._position)

    def next(self):
        self._position += 1

    def prev(self):
        self._position = (self._position - 1) % len(self._items)


class Screen(Observable):
    """Model representing one (usually physical) monitor"""

    @property
    def wallpaper(self):
        return self.wallpapers.current

    @property
    def wallpaper_scale(self):
        wp = self.wallpaper
        return wp.scale * max(self.width / wp.width, self.height / wp.height)

    def __init__(self, idx, wallpapers,  **props):
        super().__init__()
        self.idx = idx
        self.wallpapers = wallpapers
        for attr, value in props.items():
            setattr(self, attr, value)
        self.wallpaper.subscribe(self)

    def __repr__(self):
        return self.__class__.__name__ + ":" + str(self.idx)

    def __int__(self):
        return self.idx

    def __index__(self):
        return self.idx

    @observed
    def notify(self, *_):
        pass

    @observed
    def next_wallpaper(self):
        self.wallpaper.unsubscribe(self)
        self.wallpapers.next()
        self.wallpaper.subscribe(self)

    @observed
    def prev_wallpaper(self):
        self.wallpaper.unsubscribe(self)
        self.wallpapers.prev()
        self.wallpaper.subscribe(self)

    @observed
    def set_wallpapers(self, wallpapers):
        self.wallpaper.unsubscribe(self)
        self.wallpapers = wallpapers
        self.wallpaper.subscribe(self)


class ScreenController:
    """Manage available screens, cycling through them, pausing etc."""

    def __init__(self, wallpaper_controller):
        wallpaper_source = iter(wp for wp in wallpaper_controller.wallpapers
                                if wp.check_paths())
        self.screens = tuple(Screen(idx, Collection(wallpaper_source), **data)
                             for idx, data in enumerate(get_screens_data()))
        if not self.screens:
            raise Exception("No screens found.")
        log.debug("Found %d screens.", len(self.screens))
        for screen in self.screens:
            screen.subscribe(self)
        self._live_wallpaper_paths = None

    def notify(self, *_):
        self.display_wallpapers()

    def display_wallpapers(self):
        """Put currently selected wallpapers live on screens."""
        paths = tuple(screen.wallpaper.transformed(screen.width, screen.height)
                      for screen in self.screens)
        if paths != self._live_wallpaper_paths:
            self._live_wallpaper_paths = paths
            _display_wallpapers(paths)

    def cycle_collections(self):
        first = self.screens[0].wallpapers
        for s1, s2 in zip(self.screens, self.screens[1:]):
            s1.set_wallpapers(s2.wallpapers)
        self.screens[-1].set_wallpapers(first)
