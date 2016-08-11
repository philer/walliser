#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import signal
import subprocess

import curses
from PIL import Image

from glob import iglob as glob
import gzip
import codecs
import json

from operator import attrgetter
from collections import namedtuple
from functools import wraps
from random import shuffle
from time import time

from .ui import Ui
from .models import Screen, Wallpaper


def set_wallpapers(*wallpaper_paths):
    """Low level wallpaper setter using feh"""
    subprocess.call(["feh", "--bg-fill", "--no-fehbg"] + list(wallpaper_paths))


# functional programming helpers #

def noop(*_):
    """Do nothing with any number of arguments."""
    pass

def repeat(item, count=sys.maxsize):
    for _ in range(count):
        yield item

def exhaust(iterator):
    """Do nothing with every element of an iterator."""
    for _ in iterator:
        pass

def each(function, *iterators):
    """Like map() but runs immediately and returns nothing."""
    exhaust(map(function, *iterators))

def sign(x):
    """Return a numbers signum as -1, 1 or 0"""
    return 1 if x > 0 else -1 if x < 0 else 0


def dict_update_recursive(a, b):
    """Recursiveley merge dictionaries. Mutates first argument.
    """
    for key in b:
        if key in a and isinstance(a[key], dict) and isinstance(b[key], dict):
            dict_update_recursive(a[key], b[key])
        else:
            a[key] = b[key]


class modlist:
    """Like a list but keys cycle indefinitely over a sublist."""

    def __init__(self, base_list, step=1, offset=0):
        self._list = base_list
        self._len = len(base_list)
        self._step = step
        self._offset = offset

    def __bool__(self):
        return bool(self._list)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._list[(key * self._step + self._offset) % self._len]
        keys = range(
            key.start if key.start != None else 0,
            key.stop if key.stop != None else self._len,
            key.step if key.step != None else 1
        )
        return (self[i] for i in keys)

    def remove(self, item):
        self._list.remove(item)
        self._len -= 1


ImageData = namedtuple("ImageData", [
    "path",
    "width",
    "height",
    "format",
    "rating",
    "purity",
])


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


class ScreenController:
    """Manage available screens, cycling through them, pausing etc."""

    @property
    def current_screen(self):
        """Returns last (automatically) updated screen."""
        if self.active_screens:
            return self.active_screens[self._current_screen_offset]

    @property
    def selected_screen(self):
        """Return selected screen. If none is selected select current_screen."""
        return self._selected_screen

    @selected_screen.setter
    def selected_screen(self, selected_screen):
        """Return selected screen. If none is selected select current_screen."""
        self._selected_screen.selected = False
        self._selected_screen = selected_screen
        self._selected_screen.selected = True

    def __init__(self, ui, wallpaper_controller):
        self.ui = ui
        self.wallpaper_controller = wallpaper_controller

        screen_count = self._get_screen_count()
        if not screen_count:
            raise Exception("No screens found.")
        self.screen_count = screen_count
        self.ui.update_screen_count(screen_count)
        self.screens = []
        for idx in range(screen_count):
            wallpapers = modlist(
                self.wallpaper_controller.wallpapers,
                screen_count,
                idx)
            self.screens.append(Screen(self.ui, idx, wallpapers))

        self.active_screens = modlist(self.screens[:])
        self._current_screen_offset = 0
        self.current_screen.current = True
        self._selected_screen = self.screens[0]
        self._selected_screen.selected = True
        # self.update_live_screens()
        # self.run()

    def _get_screen_count(self):
        """Finds out the number of connected screens."""
        # this is kind of a hack...
        return (
            subprocess
            .check_output(["xrandr", "-q"])
            .decode("ascii")
            .count(" connected ")
        )

    def update_ui(self, *_):
        """Update the moving parts of the UI that we can influence."""
        each(self.ui.update_screen, self.screens)

    def update_live_screens(self):
        """Get each screen's current wallpaper and put them on the monitors."""
        self.wallpaper_controller.update_live_wallpapers(
            scr.current_wallpaper for scr in self.screens
        )

    def cycle_screens(self):
        """Shift entire screens array by one position."""
        for screen in self.screens:
            screen.idx = (screen.idx + 1) % self.screen_count
        self.screens = self.screens[1:] + self.screens[0:1]
        self._update_active_screens()
        self.select_prev()
        self.update_ui()
        self.update_live_screens()

    def next(self):
        """Cycle forward in the global wallpaper rotation."""
        current = self.current_screen
        if current:
            current.current = False
            self._current_screen_offset += 1
            self.current_screen.current = True
            self.current_screen.next_wallpaper()
            self.update_live_screens()

    def prev(self):
        """Cycle backward in the global wallpaper rotation."""
        current = self.current_screen
        if current:
            current.prev_wallpaper()
            self.current_screen.current = False
            self._current_screen_offset -= 1
            self.current_screen.current = True
            self.update_live_screens()

    def select(self, scr):
        """Flexible input setter for selected_screen"""
        if isinstance(scr, Screen):
            idx = scr.idx
        elif isinstance(scr, int):
            idx = scr
        elif isinstance(scr, str):
            idx = int(scr) - 1
        else:
            raise TypeError()
        # We rely on the @property setter
        self.selected_screen = self.screens[idx]

    def select_next(self):
        """Advance the selected screen to the next of all screens."""
        # We rely on the @property getter/setter
        idx = self.selected_screen.idx
        self.selected_screen = self.screens[(idx + 1) % self.screen_count]

    def select_prev(self):
        """Advance the selected screen to the next of all screens."""
        # We rely on the @property getter/setter
        idx = self.selected_screen.idx
        self.selected_screen = self.screens[(idx - 1) % self.screen_count]

    def pause_selected(self):
        self.selected_screen.paused = True
        self._update_active_screens()

    def unpause_selected(self):
        self.selected_screen.paused = False
        self._update_active_screens()

    def pause_unpause_selected(self):
        self.selected_screen.paused = not self.selected_screen.paused
        self._update_active_screens()

    def _update_active_screens(self):
        """Regenerate the list of screens used in global wallpaper rotation."""
        if self.current_screen:
            self.current_screen.current = False
        active_screens = [s for s in self.screens if not s.paused]
        if active_screens:
            self.active_screens = modlist(active_screens)
            self.current_screen.current = True
            # self.update_interval.start() # TODO remove
        else:
            self.active_screens = []
            # self.update_interval.stop() # TODO remove

    def next_on_selected(self):
        """Update selected (or current) screen to the next wallpaper."""
        self.selected_screen.next_wallpaper()
        self.update_live_screens()

    def prev_on_selected(self):
        """Update selected (or current) screen to the previous wallpaper."""
        self.selected_screen.prev_wallpaper()
        self.update_live_screens()

    def inc_rating_on_selected(self):
        """Increment rating of current wallpaper on selected screen."""
        self.selected_screen.current_wallpaper.rating += 1

    def dec_rating_on_selected(self):
        """Decrement rating of current wallpaper on selected screen."""
        self.selected_screen.current_wallpaper.rating -= 1

    def inc_purity_on_selected(self):
        """Increment purity of current wallpaper on selected screen."""
        self.selected_screen.current_wallpaper.purity += 1

    def dec_purity_on_selected(self):
        """Decrement purity of current wallpaper on selected screen."""
        self.selected_screen.current_wallpaper.purity -= 1


class Core:
    """Main entry point to the application, manages run loops."""

    def __init__(self, args):
        self.interval_delay = args.interval_delay
        with Ui() as self.ui:
            self.ui.update_interval_delay(args.interval_delay)
            self.wallpaper_controller = WallpaperController(self.ui, args)
            self.screen_controller = ScreenController(self.ui,
                self.wallpaper_controller)

            self.assign_ui_listeners()
            self.screen_controller.update_live_screens()
            self.run_event_loop()

            if args.config_file:
                self.wallpaper_controller.store_config(args.config_file)

    def assign_ui_listeners(self):
        """Set up Ui interaction keypress listeners.

        The following keyboard mappings are currently implemented/planned:
          - next/prev (global): n/b
          - next/prev (current): right/left
          - (un)pause (global): p
          - (un)pause (current): space
          - rating/purity: ws/ed (ws/ad)
          - help: h
          - quit: ESC (qQ)
        """

        keypress = self.ui.on_keypress

        # keypress('q',                self.interrupt)
        # keypress('Q',                self.interrupt)
        keypress('esc',              self.interrupt)
        signal.signal(signal.SIGINT, self.interrupt)

        def with_interval_reset(fn):
            """Some keypress listeners should reset the wallpaper interval."""
            @wraps(fn)
            def wrapper(*args):
                fn(*args)
                self.reset_interval_timeout()
            return wrapper

        def with_interval_delay(fn, delay=2):
            """Some keypress listeners should ensure a short delay before
            wallpaper rotation resumes."""
            @wraps(fn)
            def wrapper(*args):
                fn(*args)
                self.ensure_next_interval_delay(delay)
            return wrapper

        scrctrl = self.screen_controller

        keypress(curses.KEY_RESIZE, scrctrl.update_ui)

        keypress('n', with_interval_reset(scrctrl.next))
        keypress('b', with_interval_reset(scrctrl.prev))
        keypress('x', with_interval_reset(scrctrl.cycle_screens))

        keypress('tab', scrctrl.select_next)
        keypress('↓',   scrctrl.select_next)
        keypress('↑',   scrctrl.select_prev)
        keypress(' ',   scrctrl.pause_unpause_selected)

        keypress('a', with_interval_reset(scrctrl.next_on_selected))
        keypress('q', with_interval_reset(scrctrl.prev_on_selected))
        keypress('→', with_interval_reset(scrctrl.next_on_selected))
        keypress('←', with_interval_reset(scrctrl.prev_on_selected))

        keypress('w', with_interval_delay(scrctrl.inc_rating_on_selected))
        keypress('s', with_interval_delay(scrctrl.dec_rating_on_selected))
        keypress('d', with_interval_delay(scrctrl.inc_purity_on_selected))
        keypress('e', with_interval_delay(scrctrl.dec_purity_on_selected))

    def run_event_loop(self):
        """Start the event loop processing Ui events.
        This method logs thread internal Exceptions.
        """
        # wait n/10 seconds on getch(), then return ERR
        curses.halfdelay(1)
        self.interrupted = False
        self.reset_interval_timeout()
        while not self.interrupted:
            char = self.ui.root_win.getch()
            if char != curses.ERR:
                self.ui.process_keypress_listeners(char)
            # using elif so we can iterate through continuous input faster
            elif time() > self.next_update:
                self.screen_controller.next()
                self.reset_interval_timeout()

    def reset_interval_timeout(self):
        """Set the countdown for the next update back to full length."""
        self.next_update = time() + self.interval_delay

    def ensure_next_interval_delay(self, seconds):
        """Extend the current delay until the next update if necessary."""
        self.next_update = max(self.next_update, time() + seconds)

    def interrupt(self, *_):
        self.interrupted = True
