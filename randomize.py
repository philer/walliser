#!/usr/bin/env python3
import os
import sys
import signal
import subprocess
from argparse import ArgumentParser
from glob import iglob as glob
# from pathlib import Path

from threading import Thread, Event
# import time
# import asyncio
import curses

import random
import string
import json

###### Helpers ######

def die(msg):
    print("ERROR: " + msg)
    sys.exit(1)

def noop(*_):
    pass


class Interval(Thread):
    """Call a function every n seconds in a separate Thread until interrupted

    See threading.Timer for comparison.
    """

    def __init__(self, interval, function, onfail=noop):
        Thread.__init__(self)
        self.interval = interval
        self.function = function
        self.onfail = onfail #if onfail is not None else noop
        self.interrupted = Event()

    def restart(self):
        """Set the current waiting interval back to its full duration"""
        self._restart = True
        self.interrupted.set()

    def interrupt(self):
        """Stop the timer loop and don't execute anything anymore."""
        self.interrupted.set()

    def run(self):
        self.interrupted.clear()
        self._restart = False
        while not self.interrupted.wait(self.interval) or self._restart:
            if self._restart:
                self.interrupted.clear()
                self._restart = False
            else:
                try:
                    self.function()
                except Exception as exc:
                    self.onfail(exc)


##### Main Class #####

class WallpaperSetter:

    def __init__(self):
        """Gather some data, setup the UI and get going"""
        self.args = self.get_args()

        self.wallpapers = self.find_wallpapers(self.args.wallpaper_sources)

        random.shuffle(self.wallpapers)

        self.total = len(self.wallpapers)
        if self.total == 0:
            die("No wallpapers found")

        self.screen_count = self.get_screen_count()

        with WallpaperSetterUi(self) as self.ui:
            self.run()

    def get_args(self):
        parser = ArgumentParser("wallrand",
            description="Update desktop background periodically",
            epilog="Thank you and good bye."
            )
        parser.add_argument("-i", "--interval",
            help="Seconds between updates (may be float)",
            metavar="N",
            dest="wallpaper_update_delay",
            type=float,
            default=2.0
            )
        parser.add_argument("wallpaper_sources",
            help="Any number of files or directories where wallpapers can be found. Supports globbing",
            metavar="FILE/DIR",
            nargs="+",
            )
        return parser.parse_args()


    def find_wallpapers(self, patterns):
        """Return list of wallpapers in given directories via globbing."""
        wallpapers = []
        for pattern in patterns:
            pattern = os.path.expanduser(pattern)
            for file in glob(pattern):
                if os.path.isfile(file):
                    wallpapers.append(os.path.realpath(file))
                else:
                    wallpapers += self._wallpapers_in_dir(file)
        return list(set(wallpapers))

    def _wallpapers_in_dir(self, root_dir):
        """Helper function to get a list of all wallpapers in a directory"""
        wallpapers = []
        for directory, _, files in os.walk(root_dir):
            for file in files:
                wallpapers.append(os.path.realpath(os.path.join(
                    directory, file)))
        return wallpapers

    def get_screen_count(self):
        """get the number of screens"""
        # this is kind of a hack...
        return (
            subprocess
            .check_output(["xrandr", "-q"])
            .decode("ascii")
            .count(" connected ")
        )

    def run(self):
        """Set the first wallpapers and start running event loops"""

        info = "Found {} wallpapers, updating every {} seconds on {} screens"
        self.ui.set_line(0, info.format(
            self.total, self.args.wallpaper_update_delay, self.screen_count))

        self.screen_id = self.screen_count - 1
        self.current_id = self.screen_id
        self.current = self.wallpapers[0 : self.current_id + 1]

        for s in range(0, self.screen_count):
            line = "{}: file://{}".format(s, self.current[s])
            self.ui.set_line(s + 1, line)

        self.feh(self.current)


        self.ui.on_keypress(curses.KEY_LEFT,  self.rewind)
        self.ui.on_keypress(curses.KEY_UP,    self.rewind)
        self.ui.on_keypress(curses.KEY_DOWN,  self.skip_forward)
        self.ui.on_keypress(curses.KEY_RIGHT, self.skip_forward)

        self.ui_thread = Thread(target=self.ui.run_event_loop)
        self.ui_thread.start()

        self.failed = None
        self.wallpaper_update_interval = Interval(
            self.args.wallpaper_update_delay,
            self.next_wallpaper,
            self.interrupt)

        self.wallpaper_update_interval.start()

        self.ui.on_keypress('q', self.interrupt)
        signal.signal(signal.SIGINT, self.interrupt)

        self.ui_thread.join()
        self.wallpaper_update_interval.interrupt()
        if self.failed:
            raise self.failed

    # def start_wallpaper_update_interval(self):
    #     """Creates a Interval timer that will call the subsequent updates"""
    #     self.wallpaper_update_interval = Interval(
    #         self.args.wallpaper_update_delay, self.next_wallpaper)
    #     self.wallpaper_update_interval.start()

    # def restart_wallpaper_update_interval(self):
    #     """Reset the current update timer to its full duration"""
    #     self.wallpaper_update_interval.cancel()
    #     self.start_wallpaper_update_interval()

    def skip_forward(self):
        self.next_wallpaper()
        self.wallpaper_update_interval.restart()

    def rewind(self):
        self.previous_wallpaper()
        self.wallpaper_update_interval.restart()

    def interrupt(self, exc=None, *_):
        """Game over, stop everything"""
        self.wallpaper_update_interval.interrupt()
        self.ui.stop_event_loop()
        if isinstance(exc, Exception):
            self.failed = exc

    def feh(self, wallpapers):
        """Low level wallpaper setter using feh"""
        subprocess.call(["feh", "--bg-fill", "--no-fehbg"] + wallpapers)

    def set_wallpaper(self, screen_id, wallpaper):
        """High level wallpaper setter"""
        self.current[screen_id] = wallpaper
        line = "{}: file://{}".format(screen_id, wallpaper)
        self.ui.set_line(self.screen_id + 1, line)
        self.feh(self.current)

    def next_wallpaper(self):
        """Cycle forward in the multi-screen wallpaper update loop"""
        self.current_id = (self.current_id + 1) % self.total
        self.screen_id = (self.screen_id + 1) % self.screen_count
        self.set_wallpaper(self.screen_id, self.wallpapers[self.current_id])

    def previous_wallpaper(self):
        """Cycle backward in the multi-screen wallpaper update loop"""
        prev_id = (self.current_id - self.screen_count) % self.total
        self.set_wallpaper(self.screen_id, self.wallpapers[prev_id])
        self.current_id = (self.current_id - 1) % self.total
        self.screen_id = (self.screen_id - 1) % self.screen_count



class WallpaperSetterUi:
    """Curses-based text interface for WallpaperSetter"""

    def __init__(self, owner):
        self.owner = owner
        self.key_listeners = dict()
        # self.content = []

    def __enter__(self):
        self.curses_init()
        return self

    def __exit__(self, type, value, traceback):
        self.stdscr.keypad(0)
        curses.echo()
        curses.nocbreak()
        curses.endwin()

    def curses_init(self):
        self.stdscr = curses.initscr()

        # Turn off echoing of keys, and enter cbreak mode,
        # where no buffering is performed on keyboard input
        curses.noecho()
        curses.cbreak()

        # In keypad mode, escape sequences for special keys
        # (like the cursor keys) will be interpreted and
        # a special value like curses.KEY_LEFT will be returned
        self.stdscr.keypad(1)

        # # Start color, too.  Harmless if the terminal doesn't have
        # # color; user can test with has_color() later on.  The try/catch
        # # works around a minor bit of over-conscientiousness in the curses
        # # module -- the error return from C start_color() is ignorable.
        # try:
        #     start_color()
        # except:
        #     pass

        # curses.use_default_colors()

        curses.curs_set(0)
        curses.halfdelay(1)
        self.update_tty_size()

    def run_event_loop(self):
        self._run = True
        try:
            while self._run:
                char = self.stdscr.getch()
                if char == curses.ERR:
                    continue

                key = curses.keyname(char).decode("utf-8")
                self.set_line(4, "pressed key '{:s}' ({:d})".format(key, char))

                if char == curses.KEY_RESIZE:
                    self.update_tty_size()

                for listener in self.get_keypress_listeners(char):
                    listener()
        except Exception as exc:
            self.owner.interrupt(exc)

    def stop_event_loop(self):
        self._run = False


    def update_tty_size(self):
        (self.tty_height, self.tty_width) = self.stdscr.getmaxyx()
        txt = "height: {}, width: {}".format(self.tty_height, self.tty_width)
        self.set_line(3, txt)
        # self.stdscr.addstr(
        #     self.tty_height - 1,
        #     self.tty_width - 1 - len(txt),
        #     txt)

    def set_line(self, lineno, text=""):
        if lineno >= self.tty_height - 1:
            return
        if len(text) >= self.tty_width - 1:
            text = text[0 : self.tty_width - 2] + "…"
        self.stdscr.addstr(lineno, 0, text)
        self.stdscr.clrtoeol()

    def get_keypress_listeners(self, char):
        try:
            return self.key_listeners[char]
        except KeyError:
            pass
        try:
            return self.key_listeners[curses.keyname(char).decode("utf-8")]
        except KeyError:
            pass
        return []

    def on_keypress(self, key, callback):
        if key in self.key_listeners:
            self.key_listeners[key].append(callback)
        else:
            self.key_listeners[key] = [callback]



# run
if __name__ == "__main__":
    WallpaperSetter()
