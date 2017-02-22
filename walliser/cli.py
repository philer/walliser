#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from argparse import ArgumentParser

from .core import Core
from .ui import Ui
from .config import Config
# from .wallpaper import set_wallpaper_paths
# from .maintenance import find_duplicates, convert_to_hash_keys
# from .util import error, die

def main():
    """Parse command line arguments recognized by this module."""
    parser = ArgumentParser("walliser",
        description="Update desktop background periodically",
        epilog="Thank you and good bye.",
    )
    parser.add_argument("-c", "--config-file",
        help="Read and store wallpaper data in this file. JSON formatted.",
        dest="config_file",
        type=str,
        default=None,
    )
    parser.add_argument("wallpaper_sources",
        help="Any number of files or directories where wallpapers can be found. Supports globbing",
        metavar="FILE/DIR",
        nargs="*",
        # default=".",
    )
    parser.add_argument("-i", "--interval",
        help="Seconds between updates (may be float)",
        metavar="N",
        dest="interval_delay",
        type=float,
        default=5.0,
    )
    sorting_group = parser.add_mutually_exclusive_group()
    sorting_group.add_argument("-s", "--shuffle",
        help="Cycle through wallpapers in random order.",
        dest="shuffle",
        action='store_true',
        default=True,
    )
    sorting_group.add_argument("-S", "--sort",
        help="Cycle through wallpapers in alphabetical order (fully resolved path).",
        dest="shuffle",
        action='store_false',
    )
    parser.add_argument("-q", "--query",
        help="Filter wallpapers by rating and purity",
        dest="query",
        type=str,
        default="r >= 0",
    )
    parser.add_argument("--readonly",
        help="Use this flag to prevent any changes to the config file.",
        dest="readonly",
        action='store_true'
    )

    args = parser.parse_args()

    try:
        if args.config_file:
            config_file = args.config_file
        elif 'WALLISER_DATABASE_FILE' in os.environ:
            config_file = os.environ['WALLISER_DATABASE_FILE']
        else:
            config_file = os.environ['HOME'] + "/.walliser.json.gz"

        Core(Ui(), Config(config_file, args.readonly), args)

    except KeyboardInterrupt:
        print("\033[?25h") # ANSI_SHOW_CURSOR

if __name__ == "__main__":
    main()
