#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from .core import Core
from argparse import ArgumentParser

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

    parser.add_argument("--maintenance",
        help="Perform maintenance (e.g. config file update)",
        action='store_true'
    )

    args = parser.parse_args()

    if args.maintenance:
        from .maintenance import find_duplicates
        find_duplicates(args)
    elif not args.config_file and not args.wallpaper_sources:
        parser.print_usage()
        import sys
        sys.exit(1)
    else:
        Core(args)

if __name__ == "__main__":
    main()
