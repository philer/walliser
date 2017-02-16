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
    """Like a list but keys cycle indefinitely over a sublist."""

    def __init__(self, base_list, step=1, offset=0):
        self._list = base_list
        self._len = len(base_list)
        self._step = step
        self._offset = offset

    def __bool__(self):
        return bool(self._list)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._list[(key * self._step + self._offset) % self._len]
        keys = range(
            key.start if key.start != None else 0,
            key.stop if key.stop != None else self._len,
            key.step if key.step != None else 1
        )
        return (self[i] for i in keys)

    def remove(self, item):
        self._list.remove(item)
        self._len -= 1


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
ANSI_RED         = "\033[1;31m"
ANSI_YELLOW      = "\033[3;33m"
ANSI_NO_STYLE    = "\033[0m"
ANSI_CLEAR_LINE  = "\033[K"
# ANSI_CURSOR_UP   = "\033[A"
ANSI_HIDE_CURSOR = "\033[?25l"
ANSI_SHOW_CURSOR = "\033[?25h"

def info(message):
    print(message + ANSI_CLEAR_LINE)

def warning(message):
    print(ANSI_YELLOW + message + ANSI_NO_STYLE + ANSI_CLEAR_LINE)

def error(message):
    print(ANSI_RED + message + ANSI_NO_STYLE + ANSI_CLEAR_LINE + ANSI_SHOW_CURSOR)

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
