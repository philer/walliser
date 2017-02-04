#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from argparse import ArgumentParser

from .core import Core
from .config import Config
from .wallpaper import set_wallpapers
from .maintenance import find_duplicates
from .util import error, die

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
        default=2.0,
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

    parser.add_argument("--restore",
        help="Restore last wallpaper setting and exit.",
        action='store_true'
    )
    parser.add_argument("--maintenance",
        help="Perform maintenance (e.g. config file update)",
        action='store_true'
    )

    args = parser.parse_args()

    if args.restore:
        if not args.config_file:
            parser.print_help()
            die("Error: Need config file.")
        set_wallpapers(*Config(args.config_file)["restore"])
    elif args.maintenance:
        if not args.config_file:
            parser.print_help()
            die("Error: Need config file.")
        find_duplicates(Config(args.config_file))
    elif not args.config_file and not args.wallpaper_sources:
        parser.print_help()
        die("Error: Need wallpapers.")
    else:
        Core(args)

if __name__ == "__main__":
    main()
