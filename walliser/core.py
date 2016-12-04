# -*- coding: utf-8 -*-

from functools import wraps
from time import time

import signal
import curses

from .util import Observable, observed
from .config import Config
from .wallpaper import Wallpaper, WallpaperController
from .screen import Screen, ScreenController
from .ui import Ui


stats = {"saved_wallpapers": 0}


class Core:
    """Main entry point to the application, manages run loops."""

    def __init__(self, args):
        self.interval_delay = args.interval_delay
        self.timeout_callbacks = {}

        self.config = Config(args.config_file)

        self.ui = Ui()
        self.ui.update_interval_delay(args.interval_delay)

        self.wallpaper_controller = WallpaperController(
            self.ui, self.config, args)

        with self.ui:
            self.screen_controller = ScreenController(self.ui,
                self.wallpaper_controller)
            self.screen_controller.update_live_screens()

            self.assign_ui_listeners()
            self.set_timeout(self.interval_delay, self.update_wallpapers)
            self.set_timeout(5, self.save_config)
            self.run_event_loop()

        self.save_config()
        # if stats["saved_wallpapers"]:
        #     print(str(stats["saved_wallpapers"]) + " wallpaper updates saved")

    def update_wallpapers(self):
        self.screen_controller.next()
        self.set_timeout(self.interval_delay, self.update_wallpapers)

    def save_config(self):
        updated_entries = self.wallpaper_controller.update_config(self.config)
        if updated_entries and self.config.save():
            stats["saved_wallpapers"] += updated_entries
        print("{:d} entr{:s} saved ({:d} total)".format(
            updated_entries,
            "y" if updated_entries == 1 else "ies",
            stats["saved_wallpapers"]
        ))

    def increase_interval_delay(self):
        """Reduce wallpaper rotation speed by a quarter second."""
        # self.interval_delay *= 1.1
        self.interval_delay += 0.25
        self.ui.update_interval_delay(self.interval_delay)

    def reduce_interval_delay(self):
        """Increase wallpaper rotation speed by a quarter second."""
        # self.interval_delay *= 1/1.1
        self.interval_delay -= 0.25
        self.ui.update_interval_delay(self.interval_delay)

    def assign_ui_listeners(self):
        """Set up Ui interaction keypress listeners.

        The following keyboard mappings are currently implemented/planned:
          - next/prev (global): n/b
          - next/prev (current): right/left
          - (un)pause (global): p
          - (un)pause (current): space
          - rating/purity: ws/ed (ws/ad)
          - help: h
          - quit: ESC (qQ)
        """

        keypress = self.ui.on_keypress

        # keypress('q',                self.interrupt)
        # keypress('Q',                self.interrupt)
        keypress('esc',              self.interrupt)
        keypress('^Q',              self.interrupt)
        signal.signal(signal.SIGINT, self.interrupt)

        def with_interval_reset(fn):
            """Some keypress listeners should reset the wallpaper interval."""
            @wraps(fn)
            def wrapper(*args):
                fn(*args)
                self.set_timeout(self.interval_delay, self.update_wallpapers)
            return wrapper

        def with_interval_delay(fn, delay=2):
            """Some keypress listeners should ensure a short delay before
            wallpaper rotation resumes."""
            @wraps(fn)
            def wrapper(*args):
                fn(*args)
                self.extend_timeout(delay, self.update_wallpapers)
            return wrapper

        def with_config_save(fn, delay=5):
            """Some keypress listeners should cause the configuration to be saved."""
            @wraps(fn)
            def wrapper(*args):
                fn(*args)
                self.set_timeout(delay, self.save_config)
            return wrapper

        def save_now():
            del self.timeout_callbacks[self.save_config]
            self.save_config()

        keypress('^S', save_now)

        scrctrl = self.screen_controller

        keypress(curses.KEY_RESIZE, scrctrl.update_ui)

        keypress('n', with_interval_reset(scrctrl.next))
        keypress('b', with_interval_reset(scrctrl.prev))
        keypress('x', with_interval_reset(scrctrl.cycle_screens))

        keypress('-', self.reduce_interval_delay)
        keypress('+', self.increase_interval_delay)

        keypress('tab', scrctrl.select_next)
        keypress('↓',   scrctrl.select_next)
        keypress('↑',   scrctrl.select_prev)
        keypress(' ',   scrctrl.pause_unpause_selected)

        keypress('a', with_interval_reset(scrctrl.next_on_selected))
        keypress('q', with_interval_reset(scrctrl.prev_on_selected))
        keypress('→', with_interval_reset(scrctrl.next_on_selected))
        keypress('←', with_interval_reset(scrctrl.prev_on_selected))

        keypress('w', with_interval_delay(
                          with_config_save(
                              scrctrl.inc_rating_on_selected
                      )))
        keypress('s', with_interval_delay(
                          with_config_save(
                              scrctrl.dec_rating_on_selected
                      )))
        keypress('d', with_interval_delay(
                          with_config_save(
                              scrctrl.inc_purity_on_selected
                      )))
        keypress('e', with_interval_delay(
                          with_config_save(
                              scrctrl.dec_purity_on_selected
                      )))

    def set_timeout(self, delay, fn):
        self.timeout_callbacks[fn] = time() + delay

    def extend_timeout(self, min_delay, fn):
        self.timeout_callbacks[fn] = max(
            self.timeout_callbacks[fn],
            time() + min_delay
        )

    def run_event_loop(self):
        """Start the event loop processing Ui events.
        This method logs thread internal Exceptions.
        """
        # wait n/10 seconds on getch(), then return ERR
        curses.halfdelay(1)
        self.interrupted = False
        while not self.interrupted:
            char = self.ui.root_win.getch()
            if char != curses.ERR:
                self.ui.process_keypress_listeners(char)
            # using else so we can iterate through continuous input faster
            else:
                now = time()
                for fn, t in self.timeout_callbacks.copy().items():
                    if now > t:
                        del self.timeout_callbacks[fn]
                        fn()

    def interrupt(self, *_):
        self.interrupted = True

