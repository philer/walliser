#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from .core import Core
from argparse import ArgumentParser

def parse_args():
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
    # TODO maybe parse arbitrary --query expressions rather than multiple switches
    # parser.add_argument("-r", "--min-rating",
    #     help="Filter wallpapers by minimum rating",
    #     dest="min_rating",
    #     type=int,
    #     default=0,
    # )
    # parser.add_argument("-R", "--max-rating",
    #     help="Filter wallpapers by maximum rating",
    #     dest="max_rating",
    #     type=int,
    #     default=None,
    # )
    # parser.add_argument("-p", "--min-purity",
    #     help="Filter wallpapers by maximum rating",
    #     dest="min_purity",
    #     type=int,
    #     default=None,
    # )
    # parser.add_argument("-P", "--max-purity",
    #     help="Filter wallpapers by minimum rating",
    #     dest="max_purity",
    #     type=int,
    #     default=0,
    # )
    args = parser.parse_args()
    if not args.config_file and not args.wallpaper_sources:
        parser.print_usage()
        import sys
        sys.exit(1)
    return args

def main():
    Core(parse_args())

if __name__ == "__main__":
    main()
