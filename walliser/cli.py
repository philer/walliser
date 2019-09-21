#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Walliser - A tool for cycling through wallpapers.

Usage:
  walliser [-l | -t | -b | -i SECONDS]
           [-q QUERY] [-s KEY [--reverse] | -S]
           [-d DATABASE] [--readonly]
           [--quiet | -v | -vv | -vvv]
           [--] [FILES/DIRS ...]
  walliser --maintenance [-d DATABASE] [--readonly] [--quiet | -v | -vv | -vvv]
  walliser -h | --help | --version

Options:
  -q QUERY --query QUERY
                 Filter wallpapers using Python expressions.
                 [default: rating >= 0]
  -i SECONDS --interval SECONDS
                 Seconds between updates (may be float) [default: 5]
  -s KEY --sort KEY
                 Cycle through wallpapers in order sorted by attribute KEY
         --reverse
                 Sort backwards
  -b --batch     Batch Mode i.e. non-interactive - set wallpapers and exit
  -d DATABASE --database DATABASE
                 Read and store wallpaper data in this file. If not specified
                 will use WALLISER_DATABASE_FILE from environment variable or
                 default to ~/.walliser.sqlite instead.
     --readonly  Don't write anything to the database/configuration file.
  -l --list      List all wallpaper paths which match a given query
  -t --list-tags
                 Show a list of all tags with number of wallpapers and exit.
                 (respects --query)
     --remove-tag
                 Remove given tag from all wallpapers (respects --query)
     --maintenance
  -v --verbose   Show more and more info.
     --quiet     Don't write any output after exiting fullscreen.
  -h --help      Show this help message and exit.
"""

import sys
import logging
from collections import Counter

from docopt import docopt

from . import __version__, database
from .util import BufferedLogHandler, FancyLogFormatter
from .wallpaper import WallpaperController
from .screen import ScreenController
from .urwid import Ui

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

    try:
        database.initialize(args["--database"], readonly=args["--readonly"])

        if args["--maintenance"]:
            wpctrl = WallpaperController()
            delete_hashes = set()
            for wp in wpctrl.wallpapers:
                if not wp.check_paths() and wp.rating <= 0:
                    delete_hashes.add(wp.hash)
            wpctrl.save_updates()
            log.info("Deleting {} dead entries.".format(len(delete_hashes)))
            log.warning("Deleting dead entries is not implemented for sqlite")
            return 1

        wpctrl = WallpaperController(sources=args["FILES/DIRS"],
                                     query=args["--query"],
                                     sort=args["--sort"],
                                     reverse=args["--reverse"])
        if args["--list"]:
            for wp in wpctrl.wallpapers:
                if wp.paths:
                    print(*wp.paths, sep="\n")
        elif args["--list-tags"]:
            tag_counts = Counter()
            for wp in wpctrl.wallpapers:
                tag_counts.update(wp.tags)
            max_tag_width = max(map(len, tag_counts))
            for tag, count in tag_counts.most_common():
                print(f"{tag:>{max_tag_width}} {count}")
        elif args["--batch"]:
            ScreenController(wpctrl).display_wallpapers()
        else:
            # run the actual application
            logging_handler.auto_flush = False
            scrctrl = ScreenController(wpctrl)
            scrctrl.display_wallpapers()
            Ui(scrctrl, wpctrl).run_loop()
            wpctrl.save_updates()
        return 0
    except (KeyboardInterrupt, SystemExit):
        return 0
    except Exception as e:
        log.exception(str(e))
        if args["--verbose"]:
            raise
        return 1
    finally:
        log.debug("bye.")
        logging_handler.auto_flush = True
        logging_handler.flush()



if __name__ == "__main__":
    sys.exit(main())
