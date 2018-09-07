#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Walliser - A tool for cycling through wallpapers.

Usage:
  walliser [-q QUERY] [-s] [-i SECONDS]
           [-c CONFIG_FILE] [--readonly]
           [--quiet | -v | -vv | -vvv]
           [--] [FILES/DIRS ...]
  walliser --maintenance [-c CONFIG_FILE]
  walliser -h | --help | --version

Options:
  -q QUERY --query QUERY
                 Filter wallpapers using Python expressions.
                 [default: rating >= 0]
  -i SECONDS --interval SECONDS
                 Seconds between updates (may be float) [default: 5]
  -s --sort      Cycle through wallpapers in alphabetical order of path
  -c CONFIG_FILE --config-file CONFIG_FILE
                 Read and store wallpaper data in this file. If not specified
                 will use WALLISER_DATABASE_FILE from environment variable or
                 default to ~/.walliser.json.gz instead.
     --readonly  Don't write anything to the configuration file.
     --maintenance  Deprecated
  -v --verbose   Show more and more info.
     --quiet     Don't write any output after exiting fullscreen.
  -h --help      Show this help message and exit.

"""
import os
import sys
import logging

from docopt import docopt

from . import __version__
from .util import BufferedLogHandler, FancyLogFormatter
from .ui import Ui
from .config import Config
from .wallpaper import WallpaperController
from .core import Core


log = logging.getLogger(__name__)


def setup_logging(verbose=False, quiet=False):
    if quiet:
        lvl = logging.ERROR
    elif verbose:
        lvl = logging.DEBUG
    else:
        lvl = logging.INFO
    if verbose <= 1:
        fmt = "%(message)s"
    elif verbose == 2:
        fmt = "%(levelname)s (%(name)s) %(message)s"
    else:
        fmt = "%(levelname)s (%(pathname)s:%(lineno)d) %(message)s"
    root_logger = logging.getLogger(__package__)
    root_logger.setLevel(lvl)
    handler = BufferedLogHandler()
    handler.setFormatter(FancyLogFormatter(fmt))
    root_logger.addHandler(handler)
    return handler


def main():
    """application entry point"""
    args = docopt(__doc__, version=__version__)
    logging_handler = setup_logging(args["--verbose"], args["--quiet"])
    log.debug("Starting up on python %s.", sys.version)

    exitcode = 0
    try:
        if args["--config-file"]:
            config_file = args["--config-file"]
        elif 'WALLISER_DATABASE_FILE' in os.environ:
            config_file = os.environ['WALLISER_DATABASE_FILE']
        else:
            config_file = os.environ['HOME'] + "/.walliser.json.gz"
        config = Config(config_file, readonly=args["--readonly"])

        if args["--maintenance"]:
            from walliser import maintenance
            maintenance.run(config)
        else:
            ui = Ui(logging_handler)
            wallpapers = WallpaperController(
                ui,
                config,
                sources=args["FILES/DIRS"],
                query=args["--query"],
                sort=args["--sort"],
            )
            Core(ui, config, wallpapers, interval=float(args["--interval"]))
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        exitcode = 1
        log.exception(str(e))
        if args["--verbose"]:
            raise
    finally:
        log.debug("bye.")
        logging_handler.flush()
    sys.exit(exitcode)


if __name__ == "__main__":
    main()
