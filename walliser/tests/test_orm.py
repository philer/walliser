#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest

from walliser import database
from walliser.wallpaper import Wallpaper, Transformation
from datetime import datetime

@pytest.fixture
def wallpapers():
    return (
        Wallpaper(hash="100", format="JPG", height=1080, width=1920,
                  added=datetime.now(), rating=4,
                  transformation=Transformation(True, False, 180, 1, 100, 0)),
        Wallpaper(hash="101", format="PNG", height=1600, width=1200,
                  added=datetime.now(), rating=2, purity=-2,
                  tags={"tag1", "tag2"}),
    )

def test_model(wallpapers):
    wp1, wp2 = wallpapers
    del wp1.rating

def test_store_get(wallpapers):
    database.initialize(':memory:', reconnect=True)
    for wp in wallpapers:
        wp.store()
    assert tuple(Wallpaper.get()) == wallpapers


if __name__ == "__main__":
    test()
