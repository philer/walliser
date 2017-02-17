# -*- coding: utf-8 -*-

import os
import sys
import curses
from datetime import timedelta

from .util import Observable, observed
from .screen import Screen
import walliser

keys_to_signals = {
    curses.KEY_RESIZE: walliser.UI_RESIZE,
    27:                walliser.QUIT, # esc
    '^Q':              walliser.QUIT,
    '^S':              walliser.SAVE,
    'n':               walliser.NEXT,
    'b':               walliser.PREV,
    'x':               walliser.CYCLE_SCREENS,
    '-':               walliser.INCREASE_DELAY,
    '+':               walliser.REDUCE_DELAY,
    ord('\t'):         walliser.NEXT_SCREEN, # tab
    curses.KEY_DOWN:   walliser.NEXT_SCREEN,
    curses.KEY_UP:     walliser.PREV_SCREEN,
    curses.KEY_RIGHT:  walliser.NEXT_ON_SCREEN,
    curses.KEY_LEFT:   walliser.PREV_ON_SCREEN,
    ' ':               walliser.TOGGLE_SCREEN,
    'a':               walliser.NEXT_ON_SCREEN,
    'q':               walliser.PREV_ON_SCREEN,
    'w':               walliser.INCREMENT_RATING,
    's':               walliser.DECREMENT_RATING,
    'd':               walliser.INCREMENT_PURITY,
    'e':               walliser.DECREMENT_PURITY,
}

def right_pad(length, string, character=" "):
    """Extends string to given length by adding padding characters if necessary.
    If string is longer than length it will be shortened to length.
    """
    return string[0:length] + character * (length - len(string))


def crop(lines, columns, string, ellipsis="…"):
    """Shortens string to given maximum length and adds ellipsis if it does."""
    # Expressions in Python are fun O.O
    return "\n".join(
        line[ 0 : columns - len(ellipsis) ] + ellipsis
        if len(line) > columns else line
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


def rating_as_string(rating, length=5):
    return rating_string(rating, length,
        positive="★", positive_bg="☆")


def purity_as_string(purity, length=5):
    return rating_string(purity, length,
        negative="♥", negative_bg="♡", positive="~", positive_bg="♡")

def screen_to_line(screen):
    """The shortest possible user friendly description of a wallpaper."""
    return ("{selected:s} {idx:d}{current_or_paused:s}"
            " [{rating:s}][{purity:s}] {url:s}").format(
        idx=screen.idx + 1,
        selected="»" if screen.selected else " ",
        current_or_paused="*" if screen.current else
                          "P" if screen.paused else " ",
        rating=rating_as_string(screen.current_wallpaper.rating, 2),
        purity=purity_as_string(screen.current_wallpaper.purity, 2),
        url=screen.current_wallpaper.url,
    )

def screen_to_multiline(screen):
    """Double-line user friendly description of a wallpaper."""
    return ("{selected:s} {idx:d}{current:s}"
            "[{rating:s}][{purity:s}] {format:s} {width:d}x{height:d}"
            " {paused:s}\n{url:s}").format(
        idx=screen.idx + 1,
        selected="»" if screen.selected else " ",
        current="*" if screen.current else " ",
        paused="paused" if screen.paused else "      ",
        rating=rating_as_string(screen.current_wallpaper.rating, 5),
        purity=purity_as_string(screen.current_wallpaper.purity, 5),
        width=screen.current_wallpaper.width,
        height=screen.current_wallpaper.height,
        format=screen.current_wallpaper.format,
        url=screen.current_wallpaper.url,
    )


class StdOutWrapper(Observable):

    def __init__(self):
        super().__init__()
        self.text = ""

    @observed
    def write(self, txt):
        self.text += txt

    def flush(self):
        pass


class Ui:
    """Curses-based text interface for WallpaperSetter"""

    SCREEN_WINDOW_MAX_HEIGHT = 2

    def __init__(self):
        self.signal_listeners = dict()

        self.header_string = ""
        self.footer_string = ""
        self.info_string = ""
        self.screen_count = 0
        self.screen_strings = []
        # self.screen_window_height = 0
        self.wallpaper_count = 0
        self.interval_delay = 0
        # self.update_header(screen_count, wallpaper_count, interval_delay)

    def __enter__(self):
        self.stdout_wrapper = StdOutWrapper()
        self.stdout_wrapper.subscribe(self)
        self.init_curses()
        sys.stdout = self.stdout_wrapper
        self.layout()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit_curses()
        sys.stdout = sys.__stdout__
        sys.stdout.write(self.stdout_wrapper.text)


    def init_curses(self):
        """Set up curses interface. (compare curses.wrapper)"""

        os.environ.setdefault('ESCDELAY', '25')

        self.root_win = curses.initscr()

        curses.noecho()
        curses.raw()
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
        # self.root_win.nodelay(1)

    def exit_curses(self):
        """Restores terminal to its normal state. (compare curses.wrapper)"""
        self.root_win.keypad(0)
        curses.nocbreak()
        curses.noraw()
        curses.echo()
        curses.endwin()


    def process_keypress_listeners(self):
        char = self.root_win.getch()
        if char == curses.ERR:
            return False
        if char == curses.KEY_RESIZE:
            self.layout()
            self.refresh_header()
            # Not responsible for body content here, done via listener

        try:
            signal = keys_to_signals[char]
        except KeyError:
            try:
                key = curses.keyname(char).decode("utf-8")
                signal = keys_to_signals[key]
            except KeyError:
                return False
        try:
            listeners = self.signal_listeners[signal]
        except KeyError:
            return False

        for listener in listeners:
                listener()
        return True

    def on_signal(self, signal, callback):
        try:
            self.signal_listeners[signal].append(callback)
        except KeyError:
            self.signal_listeners[signal] = [callback]

    def layout(self):
        """Hardcoded ui layout.
        Call whenever window sizes need recalculating.
        """
        self.root_win.erase()

        (height, width) = self.root_win.getmaxyx()
        self.width = width # used by updates

        if height > 2:
            header_height = 2
            self.header = self.root_win.subwin(header_height, width, 0, 0)
            self.update_header()
        else:
            header_height = 0

        body_height = height - header_height
        body = self.root_win.subwin(body_height, width, header_height, 0)

        self.screen_windows = []
        if self.screen_count:
            self.screen_window_height = min(
                body_height // self.screen_count,
                Ui.SCREEN_WINDOW_MAX_HEIGHT
            )
            for idx in range(self.screen_count):
                self.screen_windows.append(body.derwin(
                    self.screen_window_height,
                    width,
                    idx * self.screen_window_height,
                    0
                ))

    def notify(self, obj, method, *args):
        if isinstance(obj, Screen):
            self.update_screen(obj)
        elif isinstance(obj, StdOutWrapper) and method == "write":
            string = args[0].strip()
            if string:
                self.info(string)

    def update_screen_count(self, screen_count):
        self.screen_count = screen_count
        self.screen_strings = [""] * screen_count
        self.layout()
        self.update_header()

    def update_wallpaper_count(self, wallpaper_count):
        self.wallpaper_count = wallpaper_count
        self.update_header()

    def update_interval_delay(self, interval_delay):
        self.interval_delay = interval_delay
        self.update_header()

    def info(self, message):
        """Set an information message visible to the user."""
        self.info_string = message
        self.update_header()

    def update_header(self):
        if not self.screen_count:
            return
        run_time = (
            self.wallpaper_count * self.interval_delay / self.screen_count)

        text = (
                "{wallpaper_count:d} wallpapers | "
                "{screen_count:d} screens | "
                "{interval_delay:.3}s "
                "({run_time}) "
            ).format(
                wallpaper_count=self.wallpaper_count,
                interval_delay=self.interval_delay,
                screen_count=self.screen_count,
                run_time=str(timedelta(seconds=int(run_time))),
            )
        text += (" " * (self.width - len(text) - len(self.info_string))
               + self.info_string
               + "\n" + ("─" * self.width))
        self.header_string = text
        self.refresh_header()

    def update_screen(self, screen):
        if self.screen_window_height == 1:
            self.screen_strings[screen.idx] = screen_to_line(screen)
        else:
            self.screen_strings[screen.idx] = screen_to_multiline(screen)

        win = self.screen_windows[screen.idx]
        if screen.selected:
            win.bkgd(' ', curses.A_BOLD) #curses.A_REVERSE
        else:
            win.bkgd(' ', curses.A_NORMAL)

        self.refresh_screen(screen.idx)

    def refresh_header(self):
        self._set_window_content(self.header, self.header_string)

    def refresh_screen(self, idx):
        self._set_window_content(
            self.screen_windows[idx],
            self.screen_strings[idx])
        # win.chgat(0, 0, curses.A_REVERSE | curses.A_BOLD)

    def _set_window_content(self, win, string):
        (height, width) = win.getmaxyx()
        win.erase()
        win.insstr(crop(height, width, string))
        win.refresh()
