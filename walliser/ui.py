# -*- coding: utf-8 -*-

import os
import curses
from datetime import timedelta


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


class Ui:
    """Curses-based text interface for WallpaperSetter"""

    SCREEN_WINDOW_MAX_HEIGHT = 2

    HEADER_TEMPLATE = ("Found {wallpaper_count:d} wallpapers,"
                       " updating every {interval_delay:.1f} seconds on"
                       " {screen_count:d} screens"
                       " ({total_run_time:s} total)"
                    )

    def __init__(self):
        self.init_curses()
        self.key_listeners = dict()

        self.header_string = ""
        self.footer_string = ""
        self.screen_count = 0
        self.screen_strings = []
        # self.screen_window_height = 0
        self.wallpaper_count = 0
        self.interval_delay = 0
        self.layout()
        # self.update_header(screen_count, wallpaper_count, interval_delay)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit_curses()

    def init_curses(self):
        """Set up curses interface. (compare curses.wrapper)"""

        os.environ.setdefault('ESCDELAY', '25')

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
        # curses.halfdelay(1)
        # self.root_win.nodelay(1)

    def exit_curses(self):
        """Restores terminal to its normal state. (compare curses.wrapper)"""
        self.root_win.keypad(0)
        curses.echo()
        curses.nocbreak()
        curses.endwin()


    def process_keypress_listeners(self, char):
        # # char = self.root_win.getch()
        # if char == curses.ERR:
        #     return False
        key = curses.keyname(char).decode("utf-8")
        self.update_footer("pressed key '{:s}' ({:d})".format(key, char))
        if char == curses.KEY_RESIZE:
            self.layout()
            self.refresh_header()
            self.refresh_footer()
            # Not responsible for body content here, done via listener
        try:
            for listener in self.key_listeners[char]:
                listener()
        except KeyError:
            pass
        try:
            for listener in self.key_listeners[key]:
                listener()
        except KeyError:
            pass

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
        body_height = height - header_height - footer_height

        # subwin/derwin args: [height, width,] top_y, left_x
        self.header = self.root_win.subwin(header_height, width, 0, 0)
        self.body = self.root_win.subwin(body_height, width, header_height, 0)
        self.footer = self.root_win.subwin(footer_height, width, height - 1, 0)

        body_padding = 1
        self.body.border()

        self.screen_windows = []
        try:
            self.screen_window_height = min(
                (body_height - 2*body_padding) // self.screen_count,
                Ui.SCREEN_WINDOW_MAX_HEIGHT)
        except ZeroDivisionError:
            pass
        else:
            for idx in range(self.screen_count):
                self.screen_windows.append(self.body.derwin(
                    self.screen_window_height,
                    width - 2*body_padding,
                    idx * self.screen_window_height + body_padding,
                    body_padding))

    def update_screen_count(self, screen_count):
        self.screen_count = screen_count
        self.screen_strings = [""] * screen_count
        self.layout()
        self.update_header()
        self.refresh_footer()

    def update_wallpaper_count(self, wallpaper_count):
        self.wallpaper_count = wallpaper_count
        self.update_header()

    def update_interval_delay(self, interval_delay):
        self.interval_delay = interval_delay
        self.update_header()

    def update_header(self):
        try:
            run_time = (
                self.wallpaper_count * self.interval_delay / self.screen_count)
        except ZeroDivisionError:
            pass
        else:
            self.header_string = Ui.HEADER_TEMPLATE.format(
                wallpaper_count=self.wallpaper_count,
                interval_delay=self.interval_delay,
                screen_count=self.screen_count,
                total_run_time=str(timedelta(seconds=int(run_time))),
            )
            self.refresh_header()

    def update_screen(self, screen):
        self.screen_strings[screen.idx] = self.screen_to_string(screen,
            self.screen_window_height == 1)

        win = self.screen_windows[screen.idx]
        if screen.selected:
            win.bkgd(' ', curses.A_BOLD) #curses.A_REVERSE
        else:
            win.bkgd(' ', curses.A_NORMAL)

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
        # win.chgat(0, 0, curses.A_REVERSE | curses.A_BOLD)

    def refresh_footer(self):
        self._set_window_content(self.footer, self.footer_string)

    def _set_window_content(self, win, string):
        (height, width) = win.getmaxyx()
        win.erase()
        win.addstr(crop(height, width - 1, string))
        win.refresh()

    def screen_to_string(self, screen, compact=0):
        if compact:
            return self.screen_to_line(screen)
        else:
            return self.screen_to_multiline(screen)

    def screen_to_line(self, screen):
        """The shortest possible user friendly description of a wallpaper."""
        return ("{selected:s} {idx:d}{current_or_paused:s}"
                " [{rating:s}][{purity:s}] {url:s}").format(
            idx=screen.idx + 1,
            selected="»" if screen.selected else " ",
            current_or_paused="*" if screen.current else
                              "·" if screen.paused else " ",
            rating=rating_as_string(screen.current_wallpaper.rating, 3),
            purity=purity_as_string(screen.current_wallpaper.purity, 3),
            url=screen.current_wallpaper.url,
        )

    def screen_to_multiline(self, screen):
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
