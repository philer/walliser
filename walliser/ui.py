# -*- coding: utf-8 -*-

import os
import sys
import curses
from datetime import timedelta
import logging

from .util import Observable, observed, clamp, crop, CallbackLogHandler
from .screen import Screen
from .core import Signal


log = logging.getLogger(__name__)

# def rating_string(value, length=5, *, positive="+", negative="-",
#                   positive_bg=" ", negative_bg=" ", padding=" ", big="∞"):
#         """Get a rating as a visually pleasing, fixed length string.

#         The following representations are tried in order to find one that
#         is short enough for the 'length' parameter:
#         (examples assuming default formatting strings)
#         > "+++  " or "--   "
#         #> "+ 30 " or "- 999" (disabled)
#         > "+3000" or "-9999"
#         #> "+ ∞  " or "- ∞"   (disabled)
#         > "+∞"    or "-∞"     (for length = 2 and value > 1)
#         > "+"     or "-"      (for length = 1 and value != 0)
#         > ""                  (for length = 0)
#         For a zero value only positive background is returned.

#         Here are some cool characters:
#         [★☆🚫☺♥♡~✦✱*♀♂♻♲]
#         """
#         def options():
#             symbol, background = (
#                     (positive, positive_bg), (negative, negative_bg)
#                 )[value < 0]
#             absval = abs(value)
#             yield absval * symbol, background
#             absval = str(absval)
#             # yield symbol + padding + absval, padding
#             yield symbol + absval, padding
#             # yield symbol + padding + big, padding
#             yield symbol + big, padding
#             yield symbol, padding
#             yield "",""

#         string, padchar = next((s,p) for s,p in options() if len(s) <= length)
#         return string.ljust(length, padchar)


# def rating_to_string(rating, length=5):
#     return rating_string(rating, length,
#         positive="★", positive_bg="☆")

# def purity_to_string(purity, length=5):
#     return rating_string(purity, length,
#         negative="♥", negative_bg="♡", positive="~", positive_bg="♡")

def screen_to_string(screen, lines):
    """User friendly description of a screen with a wallpaper."""
    # ⏩ ⏪ ⏫ ⏬ ⏭ ⏮ ⏯ ⏴ ⏵ ⏶ ⏷ ⏸ ⏹ ⏺ •
    # ❬❭❰❱❮❯❴❵❨❩⸤⸥⸢⸣ ⎱⎰⎧⎩⎡⎣ (https://en.wikipedia.org/wiki/Bracket)
    wp = screen.current_wallpaper
    if lines > 1:
        return ("{selected}{current_or_paused} "
                "[ {rating} | {purity} ] {format} {width:d}×{height:d}"
                # "{offsets}"
                " {tags}"
                "\n{selected}{url}").format(
            selected="│" if screen.is_selected else " ",
            # current="⏵" if screen.is_current else " ",
            # paused="paused" if screen.is_paused else "",
            current_or_paused="⏵" if screen.is_current else
                              "⏸" if screen.is_paused else
                              " ",
            rating=("☆" if wp.rating == 0 else "★·" + str(wp.rating)),
            purity=("♡" if wp.purity == 0 else "♥·" + str(wp.purity)),
            width=wp.width,
            height=wp.height,
            format=wp.format,
            tags="(" + ",".join(wp.tags) + ")" if wp.tags else "",
            url=wp.url,
            # offsets=(f" ({wp.x_offset:+},{wp.y_offset:+},{screen.current_wallpaper_scale:.0%})"
            #          if wp.x_offset or wp.y_offset or wp.scale != 1
            #          else "")
        )
    else:
        return ("{selected}{current_or_paused}"
                "[{rating}][{purity}] {url}").format(
            selected="│" if screen.is_selected else " ",
            current_or_paused="⏵" if screen.is_current else
                              "⏸" if screen.is_paused else
                              " ",
            rating=("☆" if wp.rating == 0 else "★") + str(wp.rating),
            purity=("♡" if wp.purity == 0 else "♥") + str(wp.purity),
            url=wp.url,
        )


def set_curses_window_content(win, string, ellipsis="…"):
    """Put a string in a curses window. Takes care of erasing and cropping."""
    height, width = win.getmaxyx()
    win.erase()
    try:
        win.addstr(crop(height, width, string, ellipsis))
    except curses.error:
        # curses likes to complain about the curser leaving the writeable
        # area after it (correctly) wrote the string.
        # Another workaround would be using insstr.
        pass
    win.refresh()


ansi_to_curses_colors = dict()
def curses_color(fg=-1, bg=-1):
    """Get curses internal color pair id, create it if it doesn't exist yet."""
    try:
        return ansi_to_curses_colors[fg,bg]
    except KeyError:
        n = 9 + len(ansi_to_curses_colors)
        curses.init_pair(n, fg, bg)
        color = curses.color_pair(n)
        ansi_to_curses_colors[fg,bg] = color
        return color


class Ui:
    """Curses-based text interface for WallpaperSetter"""

    MAX_SCREEN_WINDOW_HEIGHT = 2

    KEYS_TO_SIGNALS = {
        curses.KEY_RESIZE: Signal.UI_RESIZE,
        27:                Signal.QUIT, # esc
        '^Q':              Signal.QUIT,
        '^S':              Signal.SAVE,
        'n':               Signal.PREV,
        'm':               Signal.NEXT,
        'x':               Signal.CYCLE_SCREENS,
        '-':               Signal.INCREASE_DELAY,
        '+':               Signal.REDUCE_DELAY,
        ord('\t'):         Signal.NEXT_SCREEN, # tab
        curses.KEY_DOWN:   Signal.NEXT_SCREEN,
        curses.KEY_UP:     Signal.PREV_SCREEN,
        curses.KEY_RIGHT:  Signal.NEXT_ON_SCREEN,
        curses.KEY_LEFT:   Signal.PREV_ON_SCREEN,
        ' ':               Signal.TOGGLE_SCREEN,
        'a':               Signal.NEXT_ON_SCREEN,
        'q':               Signal.PREV_ON_SCREEN,
        'w':               Signal.INCREMENT_RATING,
        's':               Signal.DECREMENT_RATING,
        'd':               Signal.INCREMENT_PURITY,
        'e':               Signal.DECREMENT_PURITY,
        't':               Signal.TOGGLE_TAG,
        'h':               Signal.MOVE_LEFT,
        'j':               Signal.MOVE_DOWN,
        'k':               Signal.MOVE_UP,
        'l':               Signal.MOVE_RIGHT,
        'z':               Signal.ZOOM_IN,
        'u':               Signal.ZOOM_OUT,
        '1':               Signal.ZOOM_FULL,
        '0':               Signal.RESET_ZOOM,
    }

    def __init__(self):
        self.header_string = ""
        self.footer_string = ""
        self.info_string = ""
        self.screen_count = 0
        self.screen_strings = []
        # self.screen_window_height = 0
        self.wallpaper_count = 0
        self.interval = 0
        # self.update_header(screen_count, wallpaper_count, interval)

    def __enter__(self):
        self.init_curses()
        self.log_handler = CallbackLogHandler(self.info)
        logging.getLogger(__package__).addHandler(self.log_handler)
        # self.layout()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        logging.getLogger(__package__).removeHandler(self.log_handler)
        self.exit_curses()

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
        curses.mousemask(curses.BUTTON1_CLICKED)
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
        if char == curses.KEY_MOUSE:
            id, x, y, z, bstate = curses.getmouse()
            # log.debug(f"mouse event: {id}, {x}, {y}, {z}, {bstate}")
            Signal.OPEN.trigger()
        if char == curses.KEY_RESIZE:
            self.layout()
            self.refresh_header()
            # Not responsible for body content here, done via listener

        key = curses.keyname(char).decode("utf-8")
        log.debug("key: %s", key)
        try:
            signal = self.KEYS_TO_SIGNALS[char]
        except KeyError:
            try:
                signal = self.KEYS_TO_SIGNALS[key]
            except KeyError:
                return False
        signal.trigger(char=char, key=key)

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

        try:
            self.root_win.erase()
            if header_height:
                self.header_window = self.root_win.subwin(1, width, 0, 0)
                self.update_header()
                if header_height > 1:
                    self.root_win.addstr(1, 0, "─" * width, curses_color(243))

            self.screen_windows = []
            for idx in range(min(self.screen_count, height)):
                self.screen_windows.append(self.root_win.subwin(
                    screen_window_height,
                    width,
                    idx * screen_window_height + header_height,
                    0
                ))
        except curses.error:
            pass

    def notify(self, obj, method, *args):
        if isinstance(obj, Screen):
            self.update_screen(obj)
        else:
            raise NotImplemented

    def info(self, message):
        """Set an information message visible to the user."""
        self.info_string = message
        self.update_header()

    def update_screen_count(self, screen_count):
        self.screen_count = screen_count
        self.screen_strings = [""] * screen_count
        self.layout()
        self.update_header()

    def update_wallpaper_count(self, wallpaper_count):
        self.wallpaper_count = wallpaper_count
        self.update_header()

    def update_interval(self, interval):
        self.interval = interval
        self.update_header()

    def update_header(self):
        if not self.screen_count:
            return
        run_time = (self.wallpaper_count * self.interval
                                         / self.screen_count)
        _, width = self.header_window.getmaxyx()
        text = (
                "{wallpaper_count:d} wallpapers ⋮ "
                # "{screen_count:d} screens ⋮ "
                "{interval:.3}s "
                "({run_time}) "
            ).format(
                wallpaper_count=self.wallpaper_count,
                interval=self.interval,
                # screen_count=self.screen_count,
                run_time=str(timedelta(seconds=int(run_time))),
            )
        text += self.info_string.rjust(width - len(text))
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
        set_curses_window_content(self.header_window, self.header_string)

    def refresh_screen(self, idx):
        set_curses_window_content(self.screen_windows[idx],
                                  self.screen_strings[idx])
        # win.chgat(0, 0, curses.A_REVERSE | curses.A_BOLD)
