# -*- coding: utf-8 -*-

import sys
import hashlib
from time import time
from functools import wraps

def exhaust(iterator):
    """Do nothing with every element of an iterator."""
    for _ in iterator:
        pass

def each(function, *iterators):
    """Like map() but runs immediately and returns nothing."""
    exhaust(map(function, *iterators))


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
                 *, output=sys.stderr, width=80, interval=0.066):
    """Create a CLI progress bar. Returns a callback for updating it."""
    counter = " / " + str(total)
    width -= len(prefix + sep + suffix + " " + str(total) + counter)

    lastrun = time()
    state = 0

    def update(progress=None, after=""):
        nonlocal state
        if progress is None:
            progress = state + 1
        state = progress

        if progress >= total:
            output.write(ANSI_CLEAR_LINE + ANSI_SHOW_CURSOR)
            output.flush()
            return

        now = time()
        nonlocal lastrun
        if lastrun + interval > now:
            return

        fill_width = int(progress * width / total)
        text = (
              prefix
            + fill * fill_width
            + sep
            + background * (width - fill_width)
            + suffix
            + " " + str(progress) + counter
            + ANSI_CLEAR_LINE
        )
        if after:
            text += "\n" + after + ANSI_CLEAR_LINE

        # ANSI nF: put curser at the beginning of n lines up
        text += "\033[" + str(text.count("\n")) + "F" + ANSI_HIDE_CURSOR

        output.write(text)
        output.flush()

        lastrun = now
        return update
    return update
