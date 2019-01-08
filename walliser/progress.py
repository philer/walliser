# -*- coding: utf-8 -*-
# Adds progress bars and spinners to your CLI app

import sys
from time import time
from shutil import get_terminal_size
from enum import Enum
from abc import ABCMeta

# ANSI_CURSOR_UP          = "\033[A"
ANSI_HIDE_CURSOR = "\033[?25l"
ANSI_SHOW_CURSOR = "\033[?25h"

# ANSI erase in line (CSI n K)
ANSI_ERASE_TO_EOL = "\033[0K"  # same as "\033[K"
ANSI_ERASE_TO_BOL = "\033[1K"
ANSI_ERASE_LINE   = "\033[2K"

# ANSI erase display (CSI n J)
ANSI_ERASE_TO_BOTTOM    = "\033[0J"
ANSI_ERASE_TO_TOP       = "\033[1J"
ANSI_ERASE_ALL          = "\033[2J"
ANSI_ERASE_ALL_BUFFERED = "\033[3J"


def clamp(min, max, val):
    """Combination of min and max."""
    return min if val < min else max if val > max else val


class style(dict, Enum):
    """Argument presets for ProgressBar constructor."""
    ascii = {
        'prefix':      "[",
        'fill':        "=",
        'sep':         ">",
        'background':  "-",
        'suffix':      "] ",
    }
    simple= {
        'fill':        "█",
        'sub_chars':   None,
        'background':  "░",
        'suffix':      " ",
    }
    smooth = {
        'fill':        "█",
        'sub_chars':   " ▏▎▍▌▋▊▉",
        'background':  " ",
        'suffix':      "▏",
    }
    fade =   {**smooth, 'sub_chars': " ░▒▓"}
    rise =   {**smooth, 'sub_chars': " ▁▂▃▄▅▆▇"}
    blocks = {**smooth, 'sub_chars': " ▖▌▙"}
    dots =   {**smooth, 'sub_chars': "⠄⠆⡆⡇⡧⡷⣷⣿"}
    fade2 = {
        'fill':        "█",
        'sub_chars':   "░▒▓",
        'background':  "░",
    }

class frames(str, Enum):
    """Fancy frames for ProgressSpinner."""
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


class ProgressIndicator(metaclass=ABCMeta):
    """Display a progress bar on the command line.
    Settings:
        text       : any string shown below the bar
        width      : fixed width for the entire meter (including prefix/suffix)
                     If this is None the terminal width will be used
        min_width  : minimum width for the entire meter
        max_width  : maximum width for the entire meter
        output     : file descriptor to write to (needs .write and .flush)
        interval   : minimum delay between writing to output
    """
    def __init__(self, text="", width=None, min_width=0, max_width=240,
                 output=sys.stderr, interval=1/64, **non_settings):
        super().__init__()
        self.text = text
        self.width = width
        self.min_width = min_width
        self.max_width = max_width
        self.output = output
        self.interval = interval
        self.last_redraw = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.clear()

    def __iter__(self):
        return self

    def __next__(self):
        self.update()

    def update(self, text=None):
        """Forward internal counter and/or set text below bar."""
        if text is not None:
            self.text = text
        self.redraw()

    def real_width(self):
        return clamp(self.min_width,
                     self.max_width,
                     self.width or get_terminal_size()[0])

    # def get_lines(self):
    #     """Render lines of printable output.
    #     Lines are wrapped and padded to exact line width."""
    #     pass

    def __str__(self):
        """Render a printable string of the current progress bar state."""
        return "\n".join(self.get_lines())

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

    def clear(self):
        self.output.write(ANSI_ERASE_TO_BOTTOM + ANSI_SHOW_CURSOR)
        self.output.flush()


class ProgressBar(ProgressIndicator):
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
    def __init__(self, total=100, prefix="", fill="█", sub_chars=" ▏▎▍▌▋▊▉", sep="",
                 background=" ", suffix="▏", **settings):
        super().__init__(**settings)
        self.total = total
        self.prefix = prefix
        self.fill = fill
        self.sub_chars = sub_chars
        self.sep = sep
        self.background = background
        self.suffix = suffix
        self.current = 0

    def __next__(self):
        if self.current < self.total:
            self.update()
        else:
            self.clear()
            raise StopIteration

    def update(self, forward=1, text=None):
        """Forward internal counter and/or set text below bar."""
        if text is not None:
            self.text = text
        self.current += forward
        if self.current <= self.total:
            self.redraw()
        else:
            self.clear()

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
        return [self.prefix
                + self.fill * fill_width
                + sub_fill + self.sep
                + self.background * background_width
                + suffix
                ] + [ln[:width].ljust(width) for ln in self.text.split("\n")]


class ProgressSpinner(ProgressIndicator):
    def __init__(self, frames=frames.four_dots1, interval=1/16, **settings):
        """Create a CLI spinner."""
        super().__init__(interval=interval, **settings)
        self.frames = frames
        self.offset = 0

    def get_lines(self):
        frame = self.frames[self.offset % len(self.frames)]
        self.offset += 1
        width = self.real_width()
        return [(frame + " " + line)[:width].ljust(width)
                for line in self.text.split("\n")]


class IterProgressIndicator(ProgressIndicator, metaclass=ABCMeta):

    @property
    def text(self):
        return self._text.format(self.current_item)

    @text.setter
    def text(self, text):
        self._text = text

    def __init__(self, items, text="{}", **settings):
        super().__init__(items=items, text=text, **settings)
        self.items = items
        self.items_iterator = iter(self.items)

    def __next__(self):
        self.current_item = next(self.items_iterator)
        self.update()
        return self.current_item


class IterProgressBar(ProgressBar, IterProgressIndicator):
    def __init__(self, items, **settings):
        super().__init__(items=items, **settings)

    def __next__(self):
        try:
            self.current_item = next(self.items_iterator)
        except:
            self.clear()
            raise
        else:
            self.total = len(self.items) # may be updated
            self.update()
            return self.current_item


class IterProgressSpinner(ProgressSpinner, IterProgressIndicator):
    def __init__(self, items, **settings):
        super().__init__(items=items, **settings)


def progress(items, total=None, **settings):
    """Iterator decorator shows progress while iterating."""
    if not sys.stdout.isatty():
        return items
    try:
        total = len(items) if total is None else total
    except TypeError:
        return IterProgressSpinner(items=items, **settings)
    else:
        return IterProgressBar(items=items, total=total, **settings)


def progress_deco(**settings):
    """Generator decorator for showing spinners."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            return IterProgressSpinner(fn(*args, **kwargs), **settings)
        return wrapper
    return decorator


# demo
if __name__ == "__main__":
    from time import sleep
    for i in progress(range(1000), text="processing item No.{}…"):
        sleep(0.01)
