#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Walliser - A tool for cycling through wallpapers.

Usage:
  walliser [-q QUERY] [-s KEY [--reverse]] [-i SECONDS]
           [-c CONFIG_FILE] [--readonly]
           [--quiet | -v | -vv | -vvv]
           [--] [FILES/DIRS ...]
  walliser (--list | --list-tags) [-c CONFIG_FILE]
           [-q QUERY] [-s KEY [--reverse]] [--] [FILES/DIRS ...]
  walliser --maintenance [-c CONFIG_FILE] [--readonly] [--quiet | -v | -vv | -vvv]
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
  -c CONFIG_FILE --config-file CONFIG_FILE
                 Read and store wallpaper data in this file. If not specified
                 will use WALLISER_DATABASE_FILE from environment variable or
                 default to ~/.walliser.json.gz instead.
     --readonly  Don't write anything to the configuration file.
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

import os
import sys
import logging
from collections import Counter

from docopt import docopt

from . import __version__
from .util import BufferedLogHandler, FancyLogFormatter
from .config import Config
from .wallpaper import WallpaperController
from .screen import ScreenController
from .urwid import Ui
# from .core import Core


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
        if args["--config-file"]:
            config_file = args["--config-file"]
        elif 'WALLISER_DATABASE_FILE' in os.environ:
            config_file = os.environ['WALLISER_DATABASE_FILE']
        else:
            config_file = os.environ['HOME'] + "/.walliser.json.gz"
        config = Config(config_file, readonly=args["--readonly"])

        if args["--maintenance"]:
            wpctrl = WallpaperController(config=config, query="True")
            delete_hashes = set()
            for wp in wpctrl.wallpapers:
                if not wp.check_paths() and wp.rating <= 0:
                    delete_hashes.add(wp.hash)
            wpctrl.save_updates()
            log.info("Deleting {} dead entries.".format(len(delete_hashes)))
            for hash in delete_hashes:
                del config._data["wallpapers"][hash]
            return 0


        wpctrl = WallpaperController(config=config,
                                     sources=args["FILES/DIRS"],
                                     query=args["--query"],
                                     sort=args["--sort"],
                                     reverse=args["--reverse"])
        if args["--list"]:
            config.readonly = True
            for wp in wpctrl.wallpapers:
                print(wp.path)
        elif args["--list-tags"]:
            config.readonly = True
            tag_counts = Counter()
            for wp in wpctrl.wallpapers:
                tag_counts.update(wp.tags)
            max_tag_width = max(map(len, tag_counts))
            for tag, count in tag_counts.most_common():
                print(f"{tag:>{max_tag_width}} {count}")
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
