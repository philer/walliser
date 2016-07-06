#!/usr/bin/env python3
import sys
import os
import subprocess

# import asyncio
import curses
import threading
# import time

import random

import string

# from pathlib import Path
from glob import iglob as glob


def die(msg):
    print("ERROR: " + msg)
    sys.exit(1)


class WallpaperSetter:

    def get_screen_count(self):
        """get the number of screens"""
        # this is kind of a hack...
        return (
            subprocess
            .check_output(["xrandr", "-q"])
            .decode("ascii")
            .count(" connected ")
        )

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

    def feh(self, wallpapers):
        """Low level wallpaper setter using feh"""
        subprocess.call(["feh", "--bg-fill", "--no-fehbg"] + wallpapers)

    def set_wallpaper(self, screen_id, wallpaper):
        self.current[screen_id] = wallpaper
        line = "{}: file://{}".format(screen_id, wallpaper)
        self.set_line(self.screen_id + 1, line)
        self.feh(self.current)

    def next_wallpaper(self):
        self.current_id = (self.current_id + 1) % self.total
        self.screen_id = (self.screen_id + 1) % self.screen_count
        self.set_wallpaper(self.screen_id, self.wallpapers[self.current_id])

    def previous_wallpaper(self):
        """go back one wallpaper change"""
        prev_id = (self.current_id - self.screen_count) % self.total
        self.set_wallpaper(self.screen_id, self.wallpapers[prev_id])
        self.current_id = (self.current_id - 1) % self.total
        self.screen_id = (self.screen_id - 1) % self.screen_count

    def update_wallpapers(self):
        self.wallpaper_update_timer = threading.Timer(
            self.wallpaper_update_delay, self.update_wallpapers)
        self.wallpaper_update_timer.start()
        self.next_wallpaper()

    def start_wallpaper_update_timer(self):
        self.wallpaper_update_timer = threading.Timer(
            self.wallpaper_update_delay, self.update_wallpapers)
        self.wallpaper_update_timer.start()

    def reset_wallpaper_update_timer(self):
        self.wallpaper_update_timer.cancel()
        self.start_wallpaper_update_timer()

    def set_line(self, lineno, text=""):
        if lineno >= self.tty_height:
            return
        if len(text) >= self.tty_width:
            text = text[ 0 : self.tty_width - 2] + "…"
        self.stdscr.addstr(lineno, 0, text)
        self.stdscr.clrtoeol()

    def update_tty_size(self):
        (self.tty_height, self.tty_width) = self.stdscr.getmaxyx()
        txt = "height: {}, width: {}".format(self.tty_height, self.tty_width)
        self.set_line(3, txt)
        # self.stdscr.addstr(
        #     self.tty_height - 1,
        #     self.tty_width - 1 - len(txt),
        #     txt)
            

    def main(self, stdscr):
        self.stdscr = stdscr
        curses.use_default_colors()
        curses.curs_set(0)
        self.update_tty_size()

        if len(sys.argv) < 2:
            die("No wallpapers specified")
        
        # kinda clumsy arg parsing (first argument may be delay)
        try:
            self.wallpaper_update_delay = float(sys.argv[1])
            patterns = sys.argv[2:]
        except ValueError:
            self.wallpaper_update_delay = 2.0
            patterns = sys.argv[1:]
        self.wallpapers = self.find_wallpapers(patterns)

        random.shuffle(self.wallpapers)

        self.total = len(self.wallpapers)
        if self.total == 0:
            die("No wallpapers found")

        self.screen_count = self.get_screen_count()

        info = "Found {} wallpapers, updating every {} seconds on {} screens"
        self.set_line(0, info.format(
            self.total, self.wallpaper_update_delay, self.screen_count))

        self.screen_id = self.screen_count - 1
        self.current_id = self.screen_id
        self.current = self.wallpapers[0 : self.current_id + 1]
        
        for s in range(0, self.screen_count):
            line = "{}: file://{}".format(s, self.current[s])
            self.set_line(s + 1, line)

        self.feh(self.current)

        self.wallpaper_update_timer = threading.Timer(
            self.wallpaper_update_delay, self.update_wallpapers)
        self.wallpaper_update_timer.start()

        # stdscr.nodelay(True)
        curses.halfdelay(1)
        while True:
            char = stdscr.getch()
            if char == curses.ERR:
                continue

            self.set_line(4, "pressed key '{:s}' ({:d})".format(
                curses.keyname(char).decode("utf-8"), char))
            
            if char == curses.KEY_RESIZE:
                self.update_tty_size()
            elif char == curses.KEY_LEFT or char == curses.KEY_DOWN:
                self.previous_wallpaper()
                self.reset_wallpaper_update_timer()
            elif char == curses.KEY_RIGHT or char == curses.KEY_UP:
                self.next_wallpaper()
                self.reset_wallpaper_update_timer()
            elif char == ord('q'):
                self.wallpaper_update_timer.cancel()
                return
            

# run
curses.wrapper(WallpaperSetter().main)
