# -*- coding: utf-8 -*-

import subprocess
import logging
import re

from dataclasses import dataclass

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


def _feh_display_wallpapers(paths, primary=0):
    """Low level wallpaper setter using feh"""
    args = ("feh", "--bg-fill", "--no-fehbg", paths[primary]) + tuple(paths[:primary]) + tuple(paths[primary+1:])
    try:
        subprocess.run(args=args, check=True, universal_newlines=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as cpe:
        log.warning("setting wallpapers failed '%s'", paths)
        log.debug(cpe.output)
        raise


class Collection:
    """
    Collection of Wallpapers on a Screen.
    Maintains a current position in the collection and takes new items
    from a given source if required and possible. Otherwise cycles
    through previous entries.
    """
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

    def __len__(self):
        return len(self._items)

    def append(self, item):
        self._items.append(item)
        self._position = len(self._items) - 1

    def remove_current(self):
        self._items.pop(self._position)
        self._position -= 1

    def next(self):
        self._position += 1

    def prev(self):
        self._position = (self._position - 1) % len(self._items)


@dataclass
class Screen:
    """Model representing one (usually physical) monitor"""

    idx: int
    output: str
    width: int
    height: int
    wallpapers: Collection
    primary: bool = False
    connected: bool = False

    @property
    def wallpaper(self):
        return self.wallpapers.current

    @property
    def wallpaper_scale(self):
        wp = self.wallpaper
        return wp.zoom * max(self.width / wp.width, self.height / wp.height)


class ScreenController:
    """Manage available screens, cycling through them, pausing etc."""

    def __init__(self, wallpaper_controller):
        wallpaper_source = iter(wp for wp in wallpaper_controller.wallpapers
                                if wp.check_paths())
        self.screens = tuple(Screen(idx=i,
                                    wallpapers=Collection(wallpaper_source),
                                    **data)
                             for i, data in enumerate(get_screens_data()))
        if self.screens:
            log.debug("Found %d screens.", len(self.screens))
        else:
            raise Exception("No screens found.")
        self._primary_idx = next(s for s in self.screens if s.primary).idx
        self._live_wallpaper_paths = None

    def display_wallpapers(self):
        """Put currently selected wallpapers live on screens."""
        paths = tuple(screen.wallpaper.transformed(screen.width, screen.height)
                      for screen in self.screens)
        if paths != self._live_wallpaper_paths:
            self._live_wallpaper_paths = paths
            _feh_display_wallpapers(paths, primary=self._primary_idx)
            for screen in self.screens:
                screen.wallpaper.increment_views()

    def cycle_collections(self):
        first = self.screens[0].wallpapers
        for s1, s2 in zip(self.screens, self.screens[1:]):
            s1.wallpapers = s2.wallpapers
        self.screens[-1].wallpapers = first
        self.display_wallpapers()

    def move_wallpaper(self, from_idx, to_idx):
        try:
            to_collection = self.screens[to_idx].wallpapers
        except IndexError:
            log.info("Screen %g doesn't exist.", to_idx)
        else:
            from_collection = self.screens[from_idx].wallpapers
            to_collection.append(from_collection.current)
            from_collection.remove_current()
            self.display_wallpapers()
