# -*- coding: utf-8 -*-
# Adds progress bars and spinners to your CLI app

import sys
from time import time
from functools import wraps
from shutil import get_terminal_size
from enum import Enum
from textwrap import TextWrapper

ANSI_CLEAR_LINE         = "\033[K"
# ANSI_CURSOR_UP          = "\033[A"
ANSI_HIDE_CURSOR        = "\033[?25l"
ANSI_SHOW_CURSOR        = "\033[?25h"

ANSI_ERASE_TO_EOL = "\033[0K" # same as ANSI_CLEAR_LINE
ANSI_ERASE_TO_BOL = "\033[1K"
ANSI_ERASE_LINE = "\033[2K"

ANSI_ERASE_TO_BOTTOM = "\033[0J"
ANSI_ERASE_TO_TOP = "\033[1J"
ANSI_ERASE_ALL = "\033[2J"
ANSI_ERASE_ALL_BUFFERED = "\033[3J"



def throttle(seconds):
    """Decorator suppresses function calls at short time intervals."""
    def throttle_decorator(fn):
        last_run = 0
        @wraps(fn)
        def wrapper(*args, **kwargs):
            now = time()
            nonlocal last_run
            if now - last_run > seconds:
                last_run = now
                return fn(*args, **kwargs)
        return wrapper
    return throttle_decorator

def clamp(min, max, val):
    """Combination of min and max."""
    return min if val < min else max if val > max else val


def progress_deco(**settings):
    """Generator decorator for showing spinners."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            yield from progress(fn(*args, **kwargs), **settings)
        return wrapper
    return decorator


def progress(items, total=None, text="{!s}", style=None, output=sys.stderr, **settings):
    """Iterator decorator shows progress while iterating."""
    try:
        total = len(items) if total is None else total
    except TypeError:
        update = progress_spinner(output=output, **settings)
    else:
        if style is None:
            style = smooth_bar
        update = style(total=total, output=output, **settings)

    e = None
    try:
        for item in items: # may raise GeneratorExit
            update(text=text.format(item))
            yield item
    finally:
        output.write(ANSI_ERASE_TO_BOTTOM + ANSI_SHOW_CURSOR)
        output.flush()


def ascii_bar(**settings):
    """Progress bar with pure ascii defaults."""
    return progress_bar(**{'prefix':      "[",
                           'fill':        "=",
                           'sep':         "",
                           'background':  "-",
                           'suffix':      "] ",
                           **settings})


def smooth_bar(**settings):
    """Progress bar with UTF-8 eight block steps."""
    return progress_bar(**{'prefix':      "",
                           'fill':        "█",
                           'sub':         " ▏▎▍▌▋▊▉",
                           'background':  " ",
                           'suffix':      "▏",
                           **settings})

class style(dict, Enum):
    smooth = {
        'prefix':      "",
        'fill':        "█",
        'sub_chars':   " ▏▎▍▌▋▊▉",
        'background':  " ",
        'suffix':      "▏",
    }
    ascii = {
        'prefix':      "[",
        'fill':        "=",
        'sep':         ">",
        'background':  "-",
        'suffix':      "] ",
    }


class ProgressBar:
    """Display a progress bar on the command line.
    Settings:
        total      : expected number of updates
        prefix     : left edge of the bar
        fill       : character(s) repeated for completed section of the bar
        sub_chars  : characters to be used to indicate progress at a smaller
                     level than full character width
        sep        : separator between the full and empty sections of the bar
        background : fill character for the empty section of the bar
        suffix     : right edge of the bar
        text       : any string shown below the bar
        width      : fixed width for the entire meter (including prefix/suffix)
                     If this is None the terminal width will be used
        min_width  : minimum width for the entire meter
        max_width  : maximum width for the entire meter
        output     : file descriptor to write to (needs .write and .flush)
        interval   : minimum delay between writing to output
    """
    def __init__(self, total=100, prefix="", fill="█", sub_chars=None, sep="",
                 background="░", suffix=" ", text="",
                 width=None, min_width=0, max_width=240,
                 output=sys.stderr, interval=0.0375):
        for attr, val in locals().items():
            if attr != 'self':
                setattr(self, attr, val)
        self.current = 0
        self.last_redraw = 0
        self.text_wrapper = TextWrapper(replace_whitespace=False)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.output.write(ANSI_ERASE_TO_BOTTOM + ANSI_SHOW_CURSOR)
        self.output.flush()

    def __iter__(self):
        with self:
            return self

    def __next__(self):
        if self.current < self.total:
            self.update()
        else:
            raise StopIteration

    def real_width(self):
        return clamp(self.min_width,
                     self.max_width,
                     self.width or get_terminal_size()[0])

    def __str__(self):
        """Render a printable string of the current progress bar state."""
        return "\n".join(self.get_lines())

    def get_lines(self):
        """Render lines of printable output.
        Lines are wrapped and padded to exact line width."""
        done = self.current - 1
        suffix = (self.suffix
                  + str(done).rjust(len(str(self.total)))
                  + " / "
                  + str(self.total))
        width = self.real_width()
        bar_width = width - len(self.prefix + self.sep + suffix)
        if self.sub_chars:
            sub_idx = (done * bar_width * len(self.sub_chars)
                            // self.total % len(self.sub_chars))
            sub_fill = self.sub_chars[sub_idx]
        else:
            sub_fill = ""
        fill_width = done * bar_width // self.total
        background_width = bar_width - fill_width - len(self.sep + sub_fill)
        self.text_wrapper.width = width
        return [self.prefix
                + self.fill * fill_width
                + sub_fill + self.sep
                + self.background * background_width
                + suffix
                #] + [ln[:width].ljust(width) for ln in self.text.split("\n")]
                ] + self.text_wrapper.wrap(self.text)

    def update(self, forward=1, text=None):
        """Forward internal counter and/or set text below bar."""
        if text is not None:
            self.text = text
        self.current += forward
        if self.current <= self.total:
            self.redraw()
        else:
            self.output.write(ANSI_ERASE_TO_BOTTOM + ANSI_SHOW_CURSOR)
            self.output.flush()

    def redraw(self):
        """Generate real output."""
        now = time()
        if now < self.last_redraw + self.interval:
            return
        self.last_redraw = now

        lines = self.get_lines()
        # ANSI CSI n F: put curser at the beginning of n lines up
        # Things that are annoying:
        #   - ANSI_ERASE_TO_BOTTOM (CSI 0 J) from the top causes flickering
        #   - ANSI_ERASE_TO_EOL (CSI 0 K) erases character underneath cursor
        # To deal with those things we take fully padded lines from get_lines
        # and then erase everything underneath those
        self.output.write("\n".join(lines)
                          + "\n" + ANSI_ERASE_TO_BOTTOM
                          + "\033[" + str(len(lines)) + "F"
                          + ANSI_HIDE_CURSOR)
        self.output.flush()

class IterProgressBar(ProgressBar):

    @property
    def text(self):
        return self._text.format(self.current_item)

    @text.setter
    def text(self, text):
        self._text = text

    def __init__(self, items, text="{}", **settings):
        if "total" not in settings:
            settings["total"] = len(items)
        super().__init__(text=text, **settings)
        self.items = items
        self.iterable = iter(items)

    def __iter__(self):
        with self:
            self.items_iterator = iter(self.items)
            return self

    def __next__(self):
        self.current_item = next(self.items_iterator)
        self.total = len(self.items) # may be updated
        #super().__next__()
        self.update()
        return self.current_item


def progress_bar(total=100, prefix="", fill="█", sub=None, sep="",
                 background="░", suffix=" ", output=sys.stderr, interval=0.0375):
    """Create a CLI progress bar. Returns a callback for updating it."""
    counter = " / " + str(total)
    frame_width = len(prefix + sep + suffix + str(total) + counter)
    if sub:
        frame_width += 1

    current = 0
    def update(forward=1, text=""):
        nonlocal current
        current += forward
        if current >= total:
            output.write(ANSI_ERASE_TO_BOTTOM + ANSI_SHOW_CURSOR)
            output.flush()
        else:
            redraw(text)

    @throttle(interval)
    def redraw(text=""):
        term_width = get_terminal_size()[0]
        bar_width = term_width - frame_width
        fill_width = current * bar_width // total

        if sub:
            sub_idx = current * bar_width * len(sub) // total % len(sub)
            sub_fill = sub[sub_idx]
        else:
            sub_fill = ""

        lines = [ ANSI_ERASE_TO_BOTTOM
                + prefix
                + fill * fill_width
                + sub_fill
                + sep
                + background * (bar_width - fill_width - len(sep))
                + suffix
                + str(current) + counter
                ] + [ line[:term_width] for line in text.split("\n") ]

        result = "\n".join(lines)

        # ANSI nF: put curser at the beginning of n lines up
        result += "\033[" + str(len(lines)-1) + "F" + ANSI_HIDE_CURSOR
        output.write(result)
        output.flush()

    return update


class frames(str, Enum):
    jump = "___-``'´-___"
    pop = ".oO@*"
    rise = "▁▂▃▄▅▆▇█▇▆▅▄▃▁"
    shift = "▏▎▍▌▋▊▉▊▋▌▍▎"
    blocks1 = "▖▘▝▗"
    blocks2 = "▌▀▐▄"
    pulse = "█▓▒░ ░▒▓"
    arrow = "←↖↑↗→↘↓↙"
    clock = "🕐🕑🕒🕓🕔🕕🕖🕗🕘🕙🕚"
    dot =         "⠈⠐⠠⢀⡀⠄⠂⠁"
    dots =        "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏" # weird
    four_dots1 =  "⠏⠛⠹⢸⣰⣤⣆⡇"
    four_dots2 =  "⠧⠏⠛⠹⠼⠶"
    four_dots3 =  "⡖⠶⢲⣰⣤⣆"
    seven_dots =   "⣾⣽⣻⢿⡿⣟⣯⣷"

def progress_spinner(text="", frames=frames.four_dots1,
                     output=sys.stderr, interval=0.1):
    """Create a CLI spinner. Returns a callback for updating it."""
    offset = 0

    def update(text=text):
        if text is None:
            output.write(ANSI_CLEAR_LINE + ANSI_SHOW_CURSOR)
            output.flush()
        else:
            redraw(text)

    @throttle(interval)
    def redraw(text):
        nonlocal offset
        frame = frames[offset % len(frames)]
        offset += 1
        term_width, _ = get_terminal_size()
        lines = [frame + " " + line for line in text.split("\n")]
        result = "\n".join(line[:term_width] + ANSI_CLEAR_LINE for line in lines)

        # ANSI nF: put curser at the beginning of n lines up
        result += "\033[" + str(len(lines)-1) + "F" + ANSI_HIDE_CURSOR

        output.write(result)
        output.flush()

    return update
