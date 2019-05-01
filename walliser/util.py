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

def clamp(min, max, val):
    """Combination of min and max."""
    return min if val < min else max if val > max else val


def get_file_hash(path, algorithm="sha1", blocksize=1024*1024):
    hasher = hashlib.new(algorithm)
    with open(path, 'rb') as f:
        buffer = f.read(blocksize)
        while len(buffer) > 0:
            hasher.update(buffer)
            buffer = f.read(blocksize)
    return hasher.hexdigest()


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

