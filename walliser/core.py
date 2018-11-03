# -*- coding: utf-8 -*-

from functools import wraps
from time import time
import logging
import signal

from .screen import ScreenController
from .urwid import Ui

log = logging.getLogger(__name__)


class Core:
    """Main entry point to the application, manages signals and main loop."""

    def __init__(self, config, wallpaper_controller, interval=5.0):
        self.config = config
        self.wallpaper_controller = wallpaper_controller
        self.screen_controller = ScreenController(wallpaper_controller)

        self.ui = Ui(self.screen_controller, self.wallpaper_controller)
        self.ui.run_loop()

        # signal.signal(signal.SIGINT, self.interrupt)
        # self.set_timeout(self.interval, self.update_wallpapers)
        # self.set_timeout(2, self.save_config)
        # self.wallpaper_controller.save_updates()

    # Signal.INCREASE_DELAY.subscribe(self.increase_interval)
    # Signal.REDUCE_DELAY.subscribe(self.reduce_interval)
    # Signal.TOGGLE_SCREEN.subscribe(scrctrl.pause_unpause_selected)

    # def toggle_tag():
    #     tags = self.ui.input("tags: ")
    #     for tag in filter(None, map(str.strip, tags.split(','))):
    #         self.selected_wallpaper.toggle_tag(tag)
    #         self.set_timeout(10, self.save_config)
    #     self.extend_timeout(3, self.update_wallpapers)

    # def increase_interval(self):
    #     """Reduce wallpaper rotation speed by a quarter second."""
    #     # self.interval *= 1.1
    #     self.interval += 0.25
    #     self.ui.update_interval(self.interval)

    # def reduce_interval(self):
    #     """Increase wallpaper rotation speed by a quarter second."""
    #     # self.interval *= 1/1.1
    #     self.interval -= 0.25
    #     self.ui.update_interval(self.interval)

    # def set_timeout(self, delay, fn):
    #     self.timeout_callbacks[fn] = time() + delay

    # def clear_timeout(self, fn):
    #     try:
    #         del self.timeout_callbacks[fn]
    #     except KeyError:
    #         pass

    # def extend_timeout(self, min_delay, fn):
    #     self.timeout_callbacks[fn] = max(
    #         self.timeout_callbacks[fn],
    #         time() + min_delay
    #     )
