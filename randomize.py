#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# pylint: disable=too-many-instance-attributes
# pylint: disable=too-many-arguments
# pylint: disable=too-few-public-methods
# pylint: disable=R0201
# pylint: disable=W0141
# pylint: disable=W0201
# pylint: disable=W0703
#

import os
import sys
import signal
import subprocess
from argparse import ArgumentParser, Namespace
from glob import iglob as glob
# from pathlib import Path
import json

from threading import Thread, Event
# import time
# import asyncio
import curses

from operator import attrgetter
# import string
import random
from datetime import timedelta
from urllib.parse import quote as urlquote


### functional programming helpers ###

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


### string formatting helpers ###

def right_pad(length, string, character=" "):
    """Extends string to given length by adding padding characters if necessary.
    If string is longer than length it will be shortened to length.
    """
    return string[0:length] + character * (length - len(string))


def crop(lines, perline, string, ellipsis="…"):
    """Shortens string to given maximum length and adds ellipsis if it does."""
    # Expressions in Python are fun O.O
    return "\n".join(
        line[ 0 : perline - len(ellipsis) ] + ellipsis
        if len(line) > perline else line
        for line in string.split("\n")[0:lines]
    )
    # if len(string) > length:
        # return string[0 : length - len(ellipsis) ] + ellipsis
    # return string

def rating_string(value, length=5, *, positive="+", negative="-",
                  positive_bg=" ", negative_bg=" ", padding=" ", big="∞"):
        """Get a rating as a visually pleasing, fixed length string.

        The following representations are tried in order to find one that
        is short enough for the 'length' parameter:
        (examples assuming default formatting strings)
        > "+++  " or "--   "
        #> "+ 30 " or "- 999" (disabled)
        > "+3000" or "-9999"
        #> "+ ∞  " or "- ∞"   (disabled)
        > "+∞"    or "-∞"     (for length = 2 and value > 1)
        > "+"     or "-"      (for length = 1 and value != 0)
        > ""                  (for length = 0)
        For a zero value only positive background is returned.

        Here are some cool characters:
        [★☆🚫☺♥♡~✦✱*♀♂♻♲]
        """
         # This was way too much fun. x)
        (symbol, background) = [
                (positive, positive_bg), (negative, negative_bg)
            ][value < 0]

        # omg a generator!!1
        def options():
            absval = abs(value)
            yield (absval * symbol, background)
            absval = str(absval)
            # yield symbol + padding + absval, padding
            yield (symbol + absval, padding)
            # yield symbol + padding + big, padding
            yield (symbol + big, padding)
            yield (symbol, padding)
            yield ("","")

        (string, padchar) = next((s,p) for s,p in options() if len(s) <= length)
        return right_pad(length, string, padchar)


### structural helpers ###

class modlist:
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

class Interval(Thread):
    """Call a function every n seconds in a separate Thread

    Interval can be stopped (interrupted temporarily),
    started (initially or after being stopped) and
    terminated (end of the Thread).

    See threading.Timer for running something only once.
    """

    def __init__(self, delay, function, terminated=None):
        Thread.__init__(self)
        self.delay = delay
        self.function = function
        self.interrupted = Event()
        self.interrupted.set()
        self.start_running = Event()
        self.terminated = terminated if terminated else Event()

    def is_running(self):
        """Whether the interval loop is started or stopped"""
        return not self.interrupted.is_set()

    def start(self):
        if not self.is_running():
            self.interrupted.clear()
            self.start_running.set()
            if not self.is_alive():
                Thread.start(self)

    def stop(self):
        """Stop the timer loop and don't execute anything anymore."""
        self.interrupted.set()

    def toggle(self):
        if self.is_running():
            self.stop()
        else:
            self.start()

    def reset(self):
        """Set the current waiting delay back to its full duration"""
        if self.is_running():
            self.stop()
            self.start()

    def set_delay(self, delay):
        self.delay = delay
        self.reset()

    def terminate(self):
        self.terminated.set()
        self.interrupted.set()
        self.start_running.set()

    def run(self):
        try:
            while not self.terminated.is_set():
                self.start_running.wait()
                self.start_running.clear()
                while not self.interrupted.wait(self.delay):
                    self.function()
        except Exception as exc:
            self.run_exception = exc
            self.terminate()


### Models ###

def observed(method):
    """Decorator to be added on methods that should notify observers post op."""
    def wrapper(self, *args, **kwargs):
        method(self, *args, **kwargs)
        self._notify_observers()
    return wrapper

class Observable:
    def __init__(self):
        self._observers = dict()

    def subscribe(self, callback, *args):
        """Add a subscriber to this object's observer list"""
        self._observers[callback] = args

    def unsubscribe(self, callback):
        """Remove a subscriber from this object's observer list"""
        del self._observers[callback]

    def _notify_observers(self):
        for observer, args in self._observers.items():
            observer(*args)


class Wallpaper(Observable):
    """Model representing one wallpaper"""

    @property
    def rating(self):
        return self._rating

    @rating.setter
    @observed
    def rating(self, rating):
        self._rating = rating

    @property
    def sketchy(self):
        return self._sketchy

    @sketchy.setter
    @observed
    def sketchy(self, sketchy):
        self._sketchy = sketchy

    def __init__(self, path, rating=0, sketchy=0):
        Observable.__init__(self)
        self.path = path
        self.rating = rating
        self.sketchy = sketchy

    def __repr__(self):
        return self.path

    def __eq__(self, other):
        return self.path == other.path

    def __hash__(self, other):
        return hash(Wallpaper) ^ hash(self.path)

    def sketchy_as_string(self, length=5):
        return rating_string(self.sketchy, length,
            positive="♥", positive_bg="♡", negative="~")

    def rating_as_string(self, length=5):
        return rating_string(self.rating, length,
        #    positive="✱")
            positive="★", positive_bg="☆")

    def to_dict(self):
        return {
            "path":   self.path,
            "rating": self.rating,
            "sketchy": self.sketchy,
        }


class Screen(Observable):
    """Model representing one (usually physical) monitor"""

    @property
    def current_wallpaper(self):
        return self.wallpapers[self._current_wallpaper_offset]

    @property
    def current(self):
        return self._current

    @current.setter
    @observed
    def current(self, current):
        self._current = current

    @property
    def selected(self):
        return self._selected

    @selected.setter
    @observed
    def selected(self, selected):
        self._selected = selected

    @property
    def paused(self):
        return self._paused

    @paused.setter
    @observed
    def paused(self, paused):
        self._paused = paused

    def __init__(self, ui, idx, wallpapers,
            current=False, selected=False, paused=False):
        self.ui = ui
        self.idx = idx
        self.wallpapers = wallpapers
        self._current_wallpaper_offset = 0
        self._current = current
        self._selected = selected
        self._paused = paused

        Observable.__init__(self)
        self.subscribe(ui.update_screen, self)
        self.current_wallpaper.subscribe(ui.update_screen, self)
        ui.update_screen(self)

    def __repr__(self):
        return "screen:" + str(self.idx)

    @observed
    def cycle_wallpaper(self, offset):
        self.current_wallpaper.unsubscribe(self.ui.update_screen)
        self._current_wallpaper_offset += offset
        self.current_wallpaper.subscribe(self.ui.update_screen, self)

    def next_wallpaper(self):
        self.cycle_wallpaper(1)

    def prev_wallpaper(self):
        self.cycle_wallpaper(-1)

    def ui_string(self, compact=0):
        return self.ui_line() if compact else self.ui_multiline()

    def ui_line(self):
        """The shortest possible user friendly description of a wallpaper."""
        return " ".join((
            (
                  ("»" if self.selected else " ")
                + ("*" if self.current else "·" if self.paused else " ")
                + str(self.idx + 1)
            ),
               "[" + self.current_wallpaper.rating_as_string(3)
            + "][" + self.current_wallpaper.sketchy_as_string(3) + "]",
            "file://" + urlquote(self.current_wallpaper.path),
        ))

    def ui_multiline(self):
        """Double-line user friendly description of a wallpaper."""
        return " ".join((
            str(self.idx + 1),
            "[" + self.current_wallpaper.rating_as_string() + "]",
            "[" + self.current_wallpaper.sketchy_as_string() + "]",
            "current" if self.current
                else "paused " if self.paused else "       ",
            "selected" if self.selected else "          ",
        )) + "\nfile://" + urlquote(self.current_wallpaper.path)


### View ###

class Ui:
    """Curses-based text interface for WallpaperSetter"""

    SCREEN_WINDOW_MAX_HEIGHT = 2

    def __init__(self, screen_count, wallpaper_count, update_delay):
        self.init_curses()
        self.key_listeners = dict()

        self.ping=0

        self.screen_count = screen_count
        self.header_string = ""
        self.screen_strings = ["" for _ in range(screen_count)]
        self.footer_string = ""
        self.layout()
        self.update_header(screen_count, wallpaper_count, update_delay)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit_curses()

    def init_curses(self):
        """Set up curses interface. (compare curses.wrapper)"""
        self.root_win = curses.initscr()

        # Turn off echoing of keys, and enter cbreak mode,
        # where no buffering is performed on keyboard input
        curses.noecho()
        curses.cbreak()

        # In keypad mode, escape sequences for special keys
        # (like the cursor keys) will be interpreted and
        # a special value like curses.KEY_LEFT will be returned
        self.root_win.keypad(1)

        # # Start color, too.  Harmless if the terminal doesn't have
        # # color; user can test with has_color() later on.  The try/catch
        # # works around a minor bit of over-conscientiousness in the curses
        # # module -- the error return from C start_color() is ignorable.
        # try:
        #     start_color()
        # except:
        #     pass

        # curses.use_default_colors()

        # hide cursor
        curses.curs_set(0)

        # wait n/10 seconds on getch(), then return ERR
        curses.halfdelay(1)

    def exit_curses(self):
        """Restores terminal to its normal state. (compare curses.wrapper)"""
        self.root_win.keypad(0)
        curses.echo()
        curses.nocbreak()
        curses.endwin()


    def run_event_loop(self, finished):
        try:
            while not finished.is_set():
                char = self.root_win.getch()
                if char == curses.ERR:
                    continue

                key = curses.keyname(char).decode("utf-8")
                self.update_footer("pressed key '{:s}' ({:d})".format(key, char))

                if char == curses.KEY_RESIZE:
                    self.layout()
                    self.refresh_header()
                    self.refresh_footer()
                    # Not responsible for body content here, done via listener

                try:
                    for listener in self.key_listeners[char]:
                        listener(char)
                except KeyError:
                    pass
                try:
                    for listener in self.key_listeners[key]:
                        listener(key)
                except KeyError:
                    pass

        except Exception as exc:
            self.run_event_loop_exception = exc
            finished.set()

    def on_keypress(self, key, callback):
        if key in self.key_listeners:
            self.key_listeners[key].append(callback)
        else:
            self.key_listeners[key] = [callback]


    def layout(self):
        """Hardcoded ui layout.
        Call whenever window sizes need recalculating.
        """
        self.root_win.erase()

        (height, width) = self.root_win.getmaxyx()
        self.width = width # used by updates

        header_height = 1
        footer_height = 1
        max_body_height = height - header_height - footer_height
        screen_window_height = min(max_body_height // self.screen_count,
            Ui.SCREEN_WINDOW_MAX_HEIGHT)
        self.screen_window_height = screen_window_height # used by updates
        body_height = screen_window_height * self.screen_count

        self.header = self.root_win.subwin(header_height, width, 0, 0)
        self.body = self.root_win.subwin(body_height, width, header_height, 0)
        self.footer = self.root_win.subwin(
            footer_height, width, header_height + body_height, 0)

        self.screen_windows = []
        for s in range(0, self.screen_count):
            self.screen_windows.append(self.body.derwin(
                screen_window_height, width, s * screen_window_height, 0))


    def update_header(self, screen_count, wallpaper_count, update_delay):
        playtime = timedelta(seconds=int(
            wallpaper_count * update_delay / screen_count))
        self.header_string = (
            "Found {:d} wallpapers, updating every {:.1f} seconds on {:d} screens ({:s} total)"
            .format(wallpaper_count, update_delay, screen_count, str(playtime))
        )
        self.refresh_header()

    def update_screen(self, screen):
        self.screen_strings[screen.idx] = screen.ui_string(
            self.screen_window_height == 1)
        self.refresh_screen(screen.idx)

    def update_footer(self, string):
        self.footer_string = string
        self.refresh_footer()

    def refresh_header(self):
        self._set_window_content(self.header, self.header_string)

    def refresh_screen(self, idx):
        self._set_window_content(
            self.screen_windows[idx],
            self.screen_strings[idx])

    def refresh_footer(self):
        self._set_window_content(self.footer, self.footer_string)

    def _set_window_content(self, win, string):
        (height, width) = win.getmaxyx()
        win.erase()
        win.addstr(crop(height, width - 1, string))
        win.refresh()


### Controllers ###

class WallpaperController:

    KNOWN_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif"]

    def __init__(self, args):
        self.args = args

        config = Namespace(wallpapers=[])
        try:
            with open(args.config_file, "r") as config_file:
                config = Namespace(**json.load(config_file))
        except (TypeError, FileNotFoundError):
            pass
        except ValueError:
            # only raise if the file was not empty (really "malformed")
            if os.stat(args.config_file).st_size:
                raise

        if args.wallpaper_sources:
            wallpaper_paths = set(self._find_wallpapers(args.wallpaper_sources))
        else:
            wallpaper_paths = set()

        self.wallpapers = []

        # We discard wallpaper paths that our config already knows about...
        for wp_data in config.wallpapers:
            wp = Wallpaper(**wp_data)
            self.wallpapers.append(wp)
            wallpaper_paths.discard(wp.path)

        # ... and add the remaining ones as fresh instances.
        self.wallpapers += list(map(Wallpaper, wallpaper_paths))

        if not self.wallpapers:
            raise Exception("No wallpapers found.")
        self.wallpaper_count = len(self.wallpapers)

        if args.shuffle:
            self.store_config(needs_sorting=True)
            random.shuffle(self.wallpapers)
        else:
            self.wallpapers.sort(key=attrgetter("path"))
            self.store_config(needs_sorting=False)

    def store_config(self, needs_sorting=True, pretty=False):
        """Save current configuration into given file."""
        try:
            with open(self.args.config_file, "w") as config_file:
                if needs_sorting:
                    wallpapers = sorted(self.wallpapers, key=attrgetter("path"))
                else:
                    wallpapers = self.wallpapers

                data = {
                    "wallpapers": [wp.to_dict() for wp in wallpapers]
                }
                if pretty:
                    json.dump(data, config_file, indent="\t")
                else:
                    json.dump(data, config_file, separators=(",", ":"))
        except TypeError:
            pass


    def _find_wallpapers(self, patterns):
        """Returns an iterable of wallpaper paths matching the given pattern(s).
        Doesn't clear duplicates (use a set).
        """
        wallpapers = []
        for pattern in patterns:
            pattern = os.path.expanduser(pattern)
            for path in glob(pattern):
                if os.path.isfile(path):
                    wallpapers.append(os.path.realpath(path))
                else:
                    wallpapers += self._wallpapers_in_dir(path)
        return filter(self._is_image_file, wallpapers)

    def _is_image_file(self, path):
        """Rudimentary check for know filename extensions, no magic."""
        return path[path.rfind("."):].lower() in self.KNOWN_EXTENSIONS

    def _wallpapers_in_dir(self, root_dir):
        """Helper function to get a list of all wallpapers in a directory"""
        wallpapers = []
        for directory, _, files in os.walk(root_dir):
            for f in files:
                wallpapers.append(
                    os.path.realpath(os.path.join(directory, f)))
        return wallpapers

    def update_live_wallpapers(self, wallpapers):
        """Set actually visible wallpapers."""
        self.feh([wp.path for wp in wallpapers])

    def feh(self, wallpaper_paths):
        """Low level wallpaper setter using feh"""
        subprocess.call(["feh", "--bg-fill", "--no-fehbg"] + wallpaper_paths)



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
        if self._selected_screen:
            return self._selected_screen
        # elif self.current_screen:
        self.select(self.current_screen)
        return self._selected_screen

    def __init__(self, args):
        self.update_delay = args.update_delay

        self.wallpaper_controller = WallpaperController(args)

        self.screen_count = self._get_screen_count()
        if not self.screen_count:
            raise Exception("No screens found.")

        with Ui(self.screen_count,
                self.wallpaper_controller.wallpaper_count,
                self.update_delay
                ) as self.ui:

            self.screens = []
            for s in range(self.screen_count):
                wallpapers = modlist(
                    self.wallpaper_controller.wallpapers,
                    self.screen_count,
                    s)
                self.screens.append(Screen(self.ui, s, wallpapers))

            self.active_screens = modlist(self.screens[:])
            self._current_screen_offset = 0
            self.current_screen.current = True
            self._selected_screen = None

            self.update_live_screens()

            self.run()

        # pylint: disable=E1101
        if hasattr(self.ui, 'run_event_loop_exception'):
            raise self.ui.run_event_loop_exception
        if hasattr(self.update_interval, 'run_exception'):
            raise self.update_interval.run_exception

    def run(self):
        """Setup listeners and threads and start loops."""

        # thread interruption event set by the first thread that gives up
        finished = Event()
        def interrupt(*_):
            finished.set()

        for s in range(1, self.screen_count + 1):
            self.ui.on_keypress(str(s), self.select)
        self.ui.on_keypress('0', self.deselect)
        self.ui.on_keypress('p', self.toggle_selected)
        self.ui.on_keypress(ord('\t'), self.cycle_select)

        self.ui.on_keypress(curses.KEY_RIGHT, self.forward)
        self.ui.on_keypress(curses.KEY_LEFT,  self.rewind)
        self.ui.on_keypress(curses.KEY_DOWN,  self.next_on_selected)
        self.ui.on_keypress(curses.KEY_UP,    self.prev_on_selected)

        self.ui.on_keypress('+', self.inc_rating_on_selected)
        self.ui.on_keypress('-', self.dec_rating_on_selected)
        self.ui.on_keypress('n', self.inc_sketchy_on_selected)
        self.ui.on_keypress('s', self.dec_sketchy_on_selected)

        self.ui.on_keypress(curses.KEY_RESIZE, self.update_ui)

        self.ui.on_keypress('q', interrupt)
        self.ui.on_keypress('Q', interrupt)
        signal.signal(signal.SIGINT, interrupt)

        self.ui_thread = Thread(
            target=self.ui.run_event_loop,
            args=[finished]
        )
        self.ui_thread.start()

        self.update_interval = Interval(
            self.update_delay,
            self.next,
            finished
        )
        self.update_interval.start()

        finished.wait()
        self.update_interval.terminate()


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

    def next(self):
        screen = self.current_screen
        if screen:
            self.current_screen.current = False
            self._current_screen_offset += 1
            self.current_screen.current = True
            self.current_screen.next_wallpaper()
            self.update_live_screens()

    def prev(self):
        screen = self.current_screen
        if screen:
            self.current_screen.prev_wallpaper()
            self.current_screen.current = False
            self._current_screen_offset -= 1
            self.current_screen.current = True
            self.update_live_screens()

    def forward(self, _):
        self.next()
        self.update_interval.reset()

    def rewind(self, _):
        self.prev()
        self.update_interval.reset()

    def select(self, scr):
        if isinstance(scr, Screen):
            idx = scr.idx
        elif isinstance(scr, int):
            idx = scr
        elif isinstance(scr, str):
            idx = int(scr) - 1
        else:
            raise TypeError()

        try:
            self._selected_screen.selected = False
        except AttributeError:
            pass
        self._selected_screen = self.screens[idx]
        self._selected_screen.selected = True

    def deselect(self, _):
        self._selected_screen.selected = False
        self._selected_screen = None

    def cycle_select(self, _):
        idx = self.selected_screen.idx
        self.select(self.screens[(idx + 1) % self.screen_count])

    def toggle_selected(self, _):
        screen = self.selected_screen
        if screen:
            if screen.paused:
                self.unpause_selected()
            else:
                self.pause_selected()

    def pause_selected(self):
        screen = self.selected_screen
        if screen and not screen.paused:
            screen.paused = True
            self._update_active_screens()

    def unpause_selected(self):
        screen = self.selected_screen
        if screen and screen.paused:
            screen.paused = False
            self._update_active_screens()

    def _update_active_screens(self):
        self.current_screen.current = False
        active_screens = [s for s in self.screens if not s.paused]
        if active_screens:
            # We only overwrite self.active_screens if it's not empty
            # so self.select_screen can still fall back on self.current_screen
            self.active_screens = modlist(active_screens)
            self.current_screen.current = True
            self.update_interval.start()
        else:
            self.update_interval.stop()

    def next_on_selected(self, _):
        """Update selected (or current) screen to the next wallpaper."""
        self.selected_screen.next_wallpaper()
        self.update_live_screens()

    def prev_on_selected(self, _):
        """Update selected (or current) screen to the previous wallpaper."""
        self.selected_screen.prev_wallpaper()
        self.update_live_screens()

    def inc_rating_on_selected(self, _):
        """Increment rating of current wallpaper on selected screen."""
        self.selected_screen.current_wallpaper.rating += 1

    def dec_rating_on_selected(self, _):
        """Decrement rating of current wallpaper on selected screen."""
        self.selected_screen.current_wallpaper.rating -= 1

    def inc_sketchy_on_selected(self, _):
        """Increment sketchy of current wallpaper on selected screen."""
        self.selected_screen.current_wallpaper.sketchy += 1

    def dec_sketchy_on_selected(self, _):
        """Decrement sketchy of current wallpaper on selected screen."""
        self.selected_screen.current_wallpaper.sketchy -= 1



# run
if __name__ == "__main__":
    parser = ArgumentParser("wallrand",
        description="Update desktop background periodically",
        epilog="Thank you and good bye.",
    )
    parser.add_argument("-c", "--config-file",
        help="Read and store wallpaper data in this file. JSON formatted.",
        dest="config_file",
        type=str,
        default=None,
    )
    parser.add_argument("wallpaper_sources",
        help="Any number of files or directories where wallpapers can be found. Supports globbing",
        metavar="FILE/DIR",
        nargs="*",
        # default=".",
    )
    parser.add_argument("-i", "--interval",
        help="Seconds between updates (may be float)",
        metavar="N",
        dest="update_delay",
        type=float,
        default=2.0,
    )
    sorting_group = parser.add_mutually_exclusive_group()
    sorting_group.add_argument("-s", "--shuffle",
        help="Cycle through wallpapers in random order.",
        dest="shuffle",
        action='store_true',
        default=True,
    )
    sorting_group.add_argument("-S", "--sort",
        help="Cycle through wallpapers in alphabetical order (fully resolved path).",
        dest="shuffle",
        action='store_false',
    )
    # from pprint import pprint
    # pprint(parser.parse_args())
    ScreenController(parser.parse_args())
