# -*- coding: utf-8 -*-

import sys
from math import ceil
from functools import wraps
from inspect import signature
import enum
import logging
import hashlib
from datetime import datetime
from dateutil.relativedelta import relativedelta
import re

def exhaust(iterator):
    """Do nothing with every element of an iterator."""
    for _ in iterator:
        pass
# exhaust = deque(maxlen=0).extend

def each(function, *iterators):
    """Like map() but runs immediately and returns nothing."""
    exhaust(map(function, *iterators))

def clamp(min, max, val):
    """Combination of min and max."""
    return min if val < min else max if val > max else val

def crop(lines, columns, string, ellipsis="…"):
    """Shortens string to given maximum length and adds ellipsis if it does."""
    return "\n".join(line[ 0 : columns - len(ellipsis) ] + ellipsis
                     if len(line) > columns else line
                     for line in string.split("\n")[0:lines])


# Relies on undocumented implementation details in stdlib (works in 3.5, 3.6)
class _IdentityEnumDict(enum._EnumDict):
    """dict subclass that dynamically maps keys to themselves."""
    def __getitem__(self, key):
        try:
            return super().__getitem__(key)
        except KeyError:
            if key[0] == '_' == key[-1]: # overly strict _[sd]under_ check
                raise
            self[key] = key
        return key

# Relies on undocumented implementation details in stdlib (works in 3.5, 3.6)
class AutoStrEnumMeta(enum.EnumMeta):
    """Enum type that automatically assigns members their name as their value"""
    @classmethod
    def __prepare__(metacls, cls, bases):
        return _IdentityEnumDict()


class modlist:
    """Store a current position and allow cycling."""

    @property
    def current(self):
        return self[self.position]

    def __init__(self, items, position=0):
        self.items = items
        self.position = position

    def index(self, key):
        try:
            return key % len(self.items)
        except ZeroDivisionError:
            raise IndexError("modlist is empty") from None

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
        self.items = items
        self.step = step
        self.offset = offset % step

    def index(self, key):
        return key * self.step + self.offset

    def __getitem__(self, key):
        return self.items[self.index(key)]

    def __setitem__(self, key, value):
        self.items[self.index(key)] = value

    def __len__(self):
        return ceil((len(self.items) - self.offset) / self.step)

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

def observed_property(property_name, default):
    """Default must be immutable."""
    hidden_property_name = "_" + property_name
    def getter(self):
        try:
            return getattr(self, hidden_property_name)
        except AttributeError:
            return default
    def deleter(self):
        try:
            delattr(self, hidden_property_name)
        except AttributeError:
            pass
    def setter(self, value):
        if value == default:
            try:
                delattr(self, hidden_property_name)
            except AttributeError:
                pass
        else:
            setattr(self, hidden_property_name, value)
    return property(getter, observed(setter), observed(deleter))


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

# # ANSI escape sequences used to style and control output on the terminal (TTY)
# ANSI_BLACK         = "\033[30m"
# ANSI_RED           = "\033[31m"
# ANSI_GREEN         = "\033[32m"
# ANSI_YELLOW        = "\033[33m"
ANSI_BLUE          = "\033[34m"
# ANSI_PURPLE        = "\033[35m"
# ANSI_CYAN          = "\033[36m"
ANSI_RED_BOLD      = "\033[1;31m"
ANSI_YELLOW_ITALIC = "\033[3;33m"
ANSI_NO_STYLE      = "\033[0m"
ANSI_ERASE_TO_EOL  = "\033[0K"  # same as "\033[K"
ANSI_ERASE_LINE_n  = "\033[{}K"


class CallbackLogHandler(logging.Handler):
    """Log handler that calls a given function with formatted messages."""
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.argnames = signature(fn).parameters.keys()

    def emit(self, record):
        if 'message' in self.argnames:
            self.format(record)
        self.fn(**{arg: getattr(record, arg) for arg in self.argnames})


class BufferedLogHandler(logging.Handler):
    """Log handler that writes to a file descriptor only on flush."""
    def __init__(self, auto_flush=True, output=sys.stdout):
        super().__init__()
        self.auto_flush = auto_flush
        self.output = output
        self.buffer = []

    def emit(self, record):
        self.buffer.append(record)
        if self.auto_flush:
            self.flush()

    def flush(self):
        if self.buffer:
            for record in self.buffer:
                self.output.write(self.format(record) + "\n")
            self.output.flush()
            self.buffer = []


class FancyLogFormatter(logging.Formatter):
    """Log formatter for colorful terminal output."""
    styles = {
        logging.INFO:     ANSI_BLUE,
        logging.WARNING:  ANSI_YELLOW_ITALIC,
        logging.ERROR:    ANSI_RED_BOLD,
        logging.CRITICAL: ANSI_RED_BOLD,
    }

    def format(self, record):
        message = super().format(record)
        try:
            message = self.styles[record.levelno] + message + ANSI_NO_STYLE
        except KeyError:
            pass
        return message + ANSI_ERASE_TO_EOL


_time_units = {
    "s": "seconds", "M": "minutes", "H": "hours",
    "d": "days", "w": "weeks", "m": "months", "y": "years",
}

def parse_relative_time(string):
    parts = {}
    number = 0
    for match in re.findall(r"[a-zA-Z]+|[0-9]+", string):
        try:
            number = int(match)
        except ValueError:
            parts[_time_units[match]] = number
    return datetime.now() - relativedelta(**parts)
