# -*- coding: utf-8 -*-

import sys
import hashlib
from functools import wraps
from time import time
from shutil import get_terminal_size

def exhaust(iterator):
    """Do nothing with every element of an iterator."""
    for _ in iterator:
        pass

def each(function, *iterators):
    """Like map() but runs immediately and returns nothing."""
    exhaust(map(function, *iterators))

def clamp(min, max, val):
    """Combination of min and max."""
    return min if val < min else max if val > max else val

def crop(lines, columns, string, ellipsis="…"):
    """Shortens string to given maximum length and adds ellipsis if it does."""
    return "\n".join(
        line[ 0 : columns - len(ellipsis) ] + ellipsis
        if len(line) > columns else line
        for line in string.split("\n")[0:lines]
    )

def throttle(seconds):
    """Dcorator for throttling function calls."""
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


class modlist:
    """Store a current position and allow cycling."""

    @property
    def current(self):
        return self[self.position]

    def __init__(self, items, position=0):
        self.items = list(items)
        self.position = position

    def index(self, key):
        try:
            return key % len(self.items)
        except ZeroDivisionError:
            raise IndexError

    def __getitem__(self, key):
        return self.items[self.index(key)]

    def __setitem__(self, key, value):
        self.items[self.index(key)] = value

    def __bool__(self):
        return bool(self.items)

    def cycle(self, by):
        self.position = self.position + by
        return self.current

    def prev(self):
        return self.cycle(1)

    def next(self):
        return self.cycle(-1)


class steplist:
    """Like a list but keys cycle indefinitely over a sublist."""

    def __init__(self, items, step=1, offset=0):
        self.items = list(items)
        self.step = step
        self.offset = offset

    def index(self, key):
        return key * self.step + self.offset

    def __getitem__(self, key):
        return self.items[self.index(key)]

    def __setitem__(self, key, value):
        self.items[self.index(key)] = value

    def __len__(self):
        return len(self.items) // self.step

    def __bool__(self):
        return bool(self.items)


class Observable:
    """An observable object calls registered callbacks whenever one of its
    @observed methods (including @property setters) is called.
    """

    __slots__ = ('_observers',)
    def __init__(self):
        self._observers = set()

    # def transfer_observers(self, other):
    #     other._observers.update(self._observers)
    #     self._observers = set()

    def subscribe(self, subscriber):
        """Add a subscriber to this object's observer list"""
        self._observers.add(subscriber)

    def unsubscribe(self, subscriber):
        """Remove a subscriber from this object's observer list"""
        self._observers.remove(subscriber)

    def _notify_observers(self, method_name, *args, **kwargs):
        for observer in self._observers:
            observer.notify(self, method_name, *args, **kwargs)

def observed(method):
    """Decorator to be added on methods that should notify observers
    after they were executed."""
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        method(self, *args, **kwargs)
        self._notify_observers(method.__name__, *args, **kwargs)
    return wrapper



def get_file_hash(path, algorithm="sha1", blocksize=1024*1024):
    hasher = hashlib.new(algorithm)
    with open(path, 'rb') as f:
        buffer = f.read(blocksize)
        while len(buffer) > 0:
            hasher.update(buffer)
            buffer = f.read(blocksize)
    return hasher.hexdigest()
    # return base64.b64encode(hasher.digest()).decode("utf-8")


### CLI helpers ###

# ANSI escape sequences used to style and control output on the terminal (TTY)
ANSI_RED_BOLD           = "\033[1;31m"
ANSI_YELLOW_ITALIC      = "\033[3;33m"
ANSI_NO_STYLE           = "\033[0m"
ANSI_CLEAR_LINE         = "\033[K"
# ANSI_CURSOR_UP          = "\033[A"
ANSI_HIDE_CURSOR        = "\033[?25l"
ANSI_SHOW_CURSOR        = "\033[?25h"

def info(message):
    print(message + ANSI_CLEAR_LINE)

def warning(message):
    print(ANSI_YELLOW_ITALIC + message + ANSI_NO_STYLE + ANSI_CLEAR_LINE)

def error(message):
    print(ANSI_RED_BOLD + message + ANSI_NO_STYLE + ANSI_CLEAR_LINE + ANSI_SHOW_CURSOR)

def die(message="Exiting…"):
    error(message)
    sys.exit(1)


def progress_bar(total=100,
                 prefix="", fill="█", sep="", background="░", suffix="",
                 output=sys.stderr, interval=0.1):
    """Create a CLI progress bar. Returns a callback for updating it."""
    counter = " / " + str(total)
    frame_width = len(prefix + sep + suffix + " " + str(total) + counter)

    total_progress = 0
    def update(progress=1, after_text=""):
        nonlocal total_progress
        total_progress += progress
        if total_progress >= total:
            output.write(ANSI_CLEAR_LINE + ANSI_SHOW_CURSOR)
            output.flush()
        else:
            redraw(after_text)
        return update

    @throttle(interval)
    def redraw(after_text=""):
        term_width, _ = get_terminal_size()
        bar_width = term_width - frame_width
        fill_width = int(total_progress * bar_width / total)
        lines = [
              prefix
            + fill * fill_width
            + sep
            + background * (bar_width - fill_width)
            + suffix
            + " " + str(total_progress) + counter
        ] + after_text.split("\n")

        text = "\n".join(line[:term_width] + ANSI_CLEAR_LINE for line in lines)

        # ANSI nF: put curser at the beginning of n lines up
        text += "\033[" + str(len(lines)-1) + "F" + ANSI_HIDE_CURSOR
        output.write(text)
        output.flush()

    return update


def progress_spinner(lines="", frames="⠏⠛⠹⢸⣰⣤⣆⡇",
                     output=sys.stderr, interval=0.1):
    """Create a CLI spinner. Returns a callback for updating it."""
    offset = 0

    def update(lines=lines):
        if lines is None:
            output.write(ANSI_CLEAR_LINE + ANSI_SHOW_CURSOR)
            output.flush()
        else:
            redraw(lines)
        return update

    @throttle(interval)
    def redraw(lines):
        nonlocal offset
        frame = frames[offset % len(frames)]
        offset += 1
        term_width, _ = get_terminal_size()
        lines = [frame + " " + line for line in lines.split("\n")]
        text = "\n".join(line[:term_width] + ANSI_CLEAR_LINE for line in lines)

        # ANSI nF: put curser at the beginning of n lines up
        text += "\033[" + str(len(lines)-1) + "F" + ANSI_HIDE_CURSOR

        output.write(text)
        output.flush()

    return update
