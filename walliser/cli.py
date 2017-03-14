#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from argparse import ArgumentParser
import logging

from .util import BufferedLogHandler, FancyLogFormatter
from .core import Core
from .ui import Ui
from .config import Config


def parse_args():
    """Parse command line arguments recognized by this module."""
    parser = ArgumentParser("walliser",
        description="Update desktop background periodically",
        epilog="Thank you and good bye.",
    )
    parser.add_argument("-c", "--config-file",
        help="Read and store wallpaper data in this file. JSON formatted.",
        dest='config_file',
        type=str,
        default=None,
    )
    parser.add_argument("wallpaper_sources",
        help="Any number of files or directories where wallpapers can be found. Supports globbing",
        metavar="FILE/DIR",
        nargs='*',
    )
    parser.add_argument("-i", "--interval",
        help="Seconds between updates (may be float)",
        metavar="N",
        dest='interval_delay',
        type=float,
        default=5.0,
    )
    sorting_group = parser.add_mutually_exclusive_group()
    sorting_group.add_argument("-s", "--shuffle",
        help="Cycle through wallpapers in random order.",
        dest='shuffle',
        action='store_true',
        default=True,
    )
    sorting_group.add_argument("-S", "--sort",
        help="Cycle through wallpapers in alphabetical order (fully resolved path).",
        dest='shuffle',
        action='store_false',
    )
    parser.add_argument("-q", "--query",
        help="Filter wallpapers by rating and purity",
        dest='query',
        type=str,
        default="r >= 0",
    )
    parser.add_argument("--maintenance",
        help="Use this flag to prevent any changes to the config file.",
        dest='maintenance',
        action='store_true',
    )
    parser.add_argument("--readonly",
        help="Use this flag to prevent any changes to the config file.",
        dest='readonly',
        action='store_true',
    )
    parser.add_argument("-v", "--verbose",
        dest='verbose',
        action='count',
        default=0,
    )
    parser.add_argument("--quiet",
        dest='quiet',
        action='store_true',
    )

    return parser.parse_args()


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
    args = parse_args()
    logging_handler = setup_logging(args.verbose, args.quiet)
    log.debug("Starting up.")

    exitcode = 0
    try:
        if args.config_file:
            config_file = args.config_file
        elif 'WALLISER_DATABASE_FILE' in os.environ:
            config_file = os.environ['WALLISER_DATABASE_FILE']
        else:
            config_file = os.environ['HOME'] + "/.walliser.json.gz"
        config = Config(config_file, args.readonly)

        if args.maintenance:
            from walliser import maintenance
            maintenance.run(config)
        else:
            Core(Ui(logging_handler), config, args)
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        exitcode = 1
        log.exception(str(e))
        if args.verbose:
            raise
    finally:
        log.debug("bye.")
        logging_handler.flush()
    sys.exit(exitcode)


log = logging.getLogger(__name__)


if __name__ == "__main__":
    main()
