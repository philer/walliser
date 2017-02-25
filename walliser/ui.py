# -*- coding: utf-8 -*-

import os
import sys
import curses
from inspect import signature
from time import time
from datetime import timedelta

from .util import Observable, observed, clamp, crop
from .screen import Screen
import walliser

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
        def options():
            symbol, background = (
                    (positive, positive_bg), (negative, negative_bg)
                )[value < 0]
            absval = abs(value)
            yield absval * symbol, background
            absval = str(absval)
            # yield symbol + padding + absval, padding
            yield symbol + absval, padding
            # yield symbol + padding + big, padding
            yield symbol + big, padding
            yield symbol, padding
            yield "",""

        string, padchar = next((s,p) for s,p in options() if len(s) <= length)
        return string.ljust(length, padchar)


def rating_to_string(rating, length=5):
    return rating_string(rating, length,
        positive="★", positive_bg="☆")

def purity_to_string(purity, length=5):
    return rating_string(purity, length,
        negative="♥", negative_bg="♡", positive="~", positive_bg="♡")

def screen_to_string(screen, lines):
    """User friendly description of a screen with a wallpaper."""
    # ⏩ ⏪ ⏫ ⏬ ⏭ ⏮ ⏯ ⏴ ⏵ ⏶ ⏷ ⏸ ⏹ ⏺ •
    # ❬❭❰❱❮❯❴❵❨❩⸤⸥⸢⸣ ⎱⎰⎧⎩⎡⎣ (https://en.wikipedia.org/wiki/Bracket)
    wp = screen.current_wallpaper
    if lines > 1:
        return ("{selected}{current_or_paused} "
                "[{rating}][{purity}] {format} {width:d}×{height:d}"
                " {tags}"
                "\n{selected}{url}").format(
            selected="│" if screen.is_selected else " ",
            # current="⏵" if screen.is_current else " ",
            # paused="paused" if screen.is_paused else "",
            current_or_paused="⏵" if screen.is_current else
                              "⏸" if screen.is_paused else
                              " ",
            rating=rating_to_string(wp.rating, 5),
            purity=purity_to_string(wp.purity, 5),
            width=wp.width,
            height=wp.height,
            format=wp.format,
            tags="(" + ",".join(wp.tags) + ")" if wp.tags else "",
            url=wp.url,
        )
    else:
        return ("{selected}{current_or_paused}"
                "[{rating}][{purity}] {url}").format(
            selected="│" if screen.is_selected else " ",
            current_or_paused="⏵" if screen.is_current else
                              "⏸" if screen.is_paused else
                              " ",
            rating=rating_to_string(wp.rating, 2),
            purity=purity_to_string(wp.purity, 2),
            url=wp.url,
        )

ansi_to_curses_colors = dict()
def curses_color(self, fg=-1, bg=-1):
    try:
        return ansi_to_curses_colors[fg,bg]
    except KeyError:
        n = 9 + len(ansi_to_curses_colors)
        curses.init_pair(n, fg, bg)
        color = curses.color_pair(n)
        ansi_to_curses_colors[fg,bg] = color
        return color

class StdOutWrapper(Observable):
    """Observe write calls on a writable."""
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

    MAX_SCREEN_WINDOW_HEIGHT = 2

    KEYS_TO_SIGNALS = {
        curses.KEY_RESIZE: walliser.UI_RESIZE,
        27:                walliser.QUIT, # esc
        '^Q':              walliser.QUIT,
        '^S':              walliser.SAVE,
        'n':               walliser.PREV,
        'm':               walliser.NEXT,
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
        't':               walliser.TOGGLE_TAG,
    }

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
        # self.layout()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit_curses()
        sys.stdout = sys.__stdout__
        sys.stdout.write(self.stdout_wrapper.text)


    def init_curses(self):
        """Set up curses interface. (compare curses.wrapper)"""
        os.environ.setdefault('ESCDELAY', '25')
        self.root_win = curses.initscr()
        # Start color, too.  Harmless if the terminal doesn't have
        # color; user can test with has_color() later on.  The try/catch
        # works around a minor bit of over-conscientiousness in the curses
        # module -- the error return from C start_color() is ignorable.
        try:
            curses.start_color()
        except:
            pass
        else:
            curses.use_default_colors()

        curses.noecho()
        curses.raw()
        self.root_win.keypad(1)

        # hide cursor
        curses.curs_set(0)
        # self.root_win.nodelay(1)

    def exit_curses(self):
        """Restores terminal to its normal state. (compare curses.wrapper)"""
        self.root_win.keypad(0)
        curses.nocbreak()
        curses.noraw()
        curses.echo()
        curses.endwin()

    def input(self, prompt="> "):
        self.header_window.erase()
        self.header_window.addstr(0, 0, prompt)
        self.header_window.refresh()
        curses.curs_set(1)
        curses.echo()
        input = self.header_window.getstr(0, len(prompt))
        curses.noecho()
        curses.raw()
        curses.curs_set(0)
        self.update_header()
        return input.decode("utf-8")

    def process_keypress_listeners(self):
        # wait n/10 seconds on getch(), then return ERR
        curses.halfdelay(1)
        char = self.root_win.getch()

        if char == curses.ERR:
            return False
        if char == curses.KEY_RESIZE:
            self.layout()
            self.refresh_header()
            # Not responsible for body content here, done via listener

        key = curses.keyname(char).decode("utf-8")
        try:
            signal = self.KEYS_TO_SIGNALS[char]
        except KeyError:
            try:
                signal = self.KEYS_TO_SIGNALS[key]
            except KeyError:
                return False
        try:
            listeners = self.signal_listeners[signal]
        except KeyError:
            return False

        args = {"signal": signal, "char": char, "key": key}
        for listener in listeners:
                listener[0](**{key: args[key] for key in listener[1:] if key in args})
        return True

    def on_signal(self, signal, fn):
        """Add listener for given signal perserving order and duplicates."""
        fn_data = fn, *signature(fn).parameters.keys()
        try:
            self.signal_listeners[signal].append(fn_data)
        except KeyError:
            self.signal_listeners[signal] = [fn_data]

    def layout(self):
        """Hardcoded ui layout.
        Call whenever window sizes need recalculating.
        """
        height, width = self.root_win.getmaxyx()
        self.width = width
        header_height = clamp(0, 2, height - self.screen_count)
        self.screen_window_height = screen_window_height = clamp(
                0,
                self.screen_count * Ui.MAX_SCREEN_WINDOW_HEIGHT,
                height - header_height
            ) // self.screen_count

        self.root_win.erase()
        if header_height:
            self.header_window = self.root_win.subwin(1, width, 0, 0)
            self.update_header()
            if header_height > 1:
                self.root_win.insstr(1, 0, "─" * width, curses_color(243))

        self.screen_windows = []
        for idx in range(min(self.screen_count, height)):
            self.screen_windows.append(self.root_win.subwin(
                screen_window_height,
                width,
                idx * screen_window_height + header_height,
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
        run_time = (self.wallpaper_count * self.interval_delay
                                         / self.screen_count)
        _, width = self.root_win.getmaxyx()
        text = (
                "{wallpaper_count:d} wallpapers ⋮ "
                "{screen_count:d} screens ⋮ "
                "{interval_delay:.3}s "
                "({run_time}) "
            ).format(
                wallpaper_count=self.wallpaper_count,
                interval_delay=self.interval_delay,
                screen_count=self.screen_count,
                run_time=str(timedelta(seconds=int(run_time))),
            )
        text += "{: >{}s}".format(self.info_string, width - len(text))
        self.header_string = text
        self.refresh_header()

    def update_screen(self, screen):
        try:
            win = self.screen_windows[screen.idx]
        except IndexError:
            return

        self.screen_strings[screen.idx] = screen_to_string(screen,
                                            lines=self.screen_window_height)

        if screen.is_selected:
            win.bkgd(' ', curses.A_BOLD) #curses.A_REVERSE
        else:
            win.bkgd(' ', curses.A_NORMAL)

        self.refresh_screen(screen.idx)

    def refresh_header(self):
        self._set_window_content(self.header_window, self.header_string)

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

