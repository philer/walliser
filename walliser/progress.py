# -*- coding: utf-8 -*-
# Adds progress bars and spinners to your CLI app

import sys
from time import time
from functools import wraps
from shutil import get_terminal_size

ANSI_CLEAR_LINE         = "\033[K"
# ANSI_CURSOR_UP          = "\033[A"
ANSI_HIDE_CURSOR        = "\033[?25l"
ANSI_SHOW_CURSOR        = "\033[?25h"


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

    try:
        for item in items:
            update(text=text.format(item))
            yield item
    finally:
        output.write(ANSI_CLEAR_LINE + ANSI_SHOW_CURSOR)
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
            output.write(ANSI_CLEAR_LINE + ANSI_SHOW_CURSOR)
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

        lines = [ ANSI_CLEAR_LINE
                + prefix
                + fill * fill_width
                + sub_fill
                + sep
                + background * (bar_width - fill_width - len(sep))
                + suffix
                + str(current) + counter
                ] + [ line[:term_width] for line in text.split("\n") ]

        result = ("\n" + ANSI_CLEAR_LINE).join(lines)

        # ANSI nF: put curser at the beginning of n lines up
        result += "\033[" + str(len(lines)-1) + "F" + ANSI_HIDE_CURSOR
        output.write(result)
        output.flush()

    return update


frames = {
    'jump':    "___-``'´-___",
    'pop':     ".oO@*",
    'rise':    "▁▂▃▄▅▆▇█▇▆▅▄▃▁",
    'shift':   "▏▎▍▌▋▊▉▊▋▌▍▎",
    'blocks1': "▖▘▝▗",
    'blocks2': "▌▀▐▄",
    'pulse':   "█▓▒░ ░▒▓",
    'arrow':   "←↖↑↗→↘↓↙",
    'clock':   "🕐🕑🕒🕓🕔🕕🕖🕗🕘🕙🕚",
    'dot':     "⠈⠐⠠⢀⡀⠄⠂⠁",
    'dots':    "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏", # weird
    '4dots1':  "⠏⠛⠹⢸⣰⣤⣆⡇",
    '4dots2':  "⠧⠏⠛⠹⠼⠶",
    '4dots3':  "⡖⠶⢲⣰⣤⣆",
    '7dots':   "⣾⣽⣻⢿⡿⣟⣯⣷",
}

def progress_spinner(text="", frames=frames['4dots1'],
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
