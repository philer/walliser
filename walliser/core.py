# -*- coding: utf-8 -*-

from functools import wraps
from time import time

import signal
import curses

from .util import Observable, observed
from .wallpaper import Wallpaper, WallpaperController
from .screen import Screen, ScreenController
from .ui import Ui


class Core:
    """Main entry point to the application, manages run loops."""

    def __init__(self, args):
        self.interval_delay = args.interval_delay
        with Ui() as self.ui:
            self.ui.update_interval_delay(args.interval_delay)
            self.wallpaper_controller = WallpaperController(self.ui, args)
            self.screen_controller = ScreenController(self.ui,
                self.wallpaper_controller)

            self.assign_ui_listeners()
            self.screen_controller.update_live_screens()
            self.run_event_loop()

            if args.config_file:
                self.wallpaper_controller.store_config(args.config_file)

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
        signal.signal(signal.SIGINT, self.interrupt)

        def with_interval_reset(fn):
            """Some keypress listeners should reset the wallpaper interval."""
            @wraps(fn)
            def wrapper(*args):
                fn(*args)
                self.reset_interval_timeout()
            return wrapper

        def with_interval_delay(fn, delay=2):
            """Some keypress listeners should ensure a short delay before
            wallpaper rotation resumes."""
            @wraps(fn)
            def wrapper(*args):
                fn(*args)
                self.ensure_next_interval_delay(delay)
            return wrapper

        scrctrl = self.screen_controller

        keypress(curses.KEY_RESIZE, scrctrl.update_ui)

        keypress('n', with_interval_reset(scrctrl.next))
        keypress('b', with_interval_reset(scrctrl.prev))
        keypress('x', with_interval_reset(scrctrl.cycle_screens))

        keypress('+', self.reduce_interval_delay)
        keypress('-', self.increase_interval_delay)

        keypress('tab', scrctrl.select_next)
        keypress('↓',   scrctrl.select_next)
        keypress('↑',   scrctrl.select_prev)
        keypress(' ',   scrctrl.pause_unpause_selected)

        keypress('a', with_interval_reset(scrctrl.next_on_selected))
        keypress('q', with_interval_reset(scrctrl.prev_on_selected))
        keypress('→', with_interval_reset(scrctrl.next_on_selected))
        keypress('←', with_interval_reset(scrctrl.prev_on_selected))

        keypress('w', with_interval_delay(scrctrl.inc_rating_on_selected))
        keypress('s', with_interval_delay(scrctrl.dec_rating_on_selected))
        keypress('d', with_interval_delay(scrctrl.inc_purity_on_selected))
        keypress('e', with_interval_delay(scrctrl.dec_purity_on_selected))

    def run_event_loop(self):
        """Start the event loop processing Ui events.
        This method logs thread internal Exceptions.
        """
        # wait n/10 seconds on getch(), then return ERR
        curses.halfdelay(1)
        self.interrupted = False
        self.reset_interval_timeout()
        while not self.interrupted:
            char = self.ui.root_win.getch()
            if char != curses.ERR:
                self.ui.process_keypress_listeners(char)
            # using elif so we can iterate through continuous input faster
            elif time() > self.next_update:
                self.screen_controller.next()
                self.reset_interval_timeout()

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

    def reset_interval_timeout(self):
        """Set the countdown for the next update back to full length."""
        self.next_update = time() + self.interval_delay

    def ensure_next_interval_delay(self, seconds):
        """Extend the current delay until the next update if necessary."""
        self.next_update = max(self.next_update, time() + seconds)

    def interrupt(self, *_):
        self.interrupted = True
