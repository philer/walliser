#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migrate wallpaper data from a pervious version config file to the database.
"""

import os

from . import database
from .config import Config
from .wallpaper import Wallpaper, Transformation
from .progress import progress


def wallpapers():
    """collect wallpapers from old config and convert data structure"""
    config = Config(readonly=True)
    for hash, data in progress(config["wallpapers"].items()):
        wp = Wallpaper(hash=hash, **data)
        wp.transformation = Transformation(
            *getattr(wp, "transformations", (False, False, 0)),
            getattr(wp, "zoom", 1.0),
            getattr(wp, "x_offset", 0),
            getattr(wp, "y_offset", 0),
        )
        yield wp

def main():
    database.initialize()

    # store in database
    Wallpaper.store_many(wallpapers())


if __name__ == "__main__":
    main()
