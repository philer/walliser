# -*- coding: utf-8 -*-

from functools import wraps
from time import time

import signal

from .wallpaper import WallpaperController
from .screen import ScreenController
import walliser

class Core:
    """Main entry point to the application, manages signals and main loop."""

    def __init__(self, ui, config, args):
        self.config = config
        self.ui = ui
        self.wallpaper_controller = WallpaperController(ui, config, args)

        self.stats = {"wallpaper_updates": 0}
        self.timeout_callbacks = {}
        self.interval_delay = args.interval_delay
        self.ui.update_interval_delay(args.interval_delay)

        with self.ui:
            self.screen_controller = ScreenController(ui,
                                                    self.wallpaper_controller)
            self.screen_controller.update_live_screens()

            signal.signal(signal.SIGINT, self.interrupt)
            self.assign_ui_listeners()
            self.set_timeout(self.interval_delay, self.update_wallpapers)
            self.set_timeout(5, self.save_config)
            self.run_event_loop()

        self.save_config()

    def save_config(self):
        wallpaper_updates = self.wallpaper_controller.updated_json()
        if wallpaper_updates:
            self.config["wallpapers"].update(wallpaper_updates)
            self.config.save()

        updates_count =  len(wallpaper_updates)
        self.stats["wallpaper_updates"] += updates_count
        print("{} update{} saved ({} total)".format(
            updates_count,
            "" if updates_count == 1 else "s",
            self.stats["wallpaper_updates"]
        ))

    def assign_ui_listeners(self):
        """Set up Ui interaction listeners."""
        def with_interval_reset(fn):
            """Some signals should reset the pending rotation timeout."""
            @wraps(fn)
            def wrapper(*args):
                fn(*args)
                self.set_timeout(self.interval_delay, self.update_wallpapers)
            return wrapper

        def with_interval_delay(fn, delay=2):
            """Some signals should add a short delay before rotation resumes."""
            @wraps(fn)
            def wrapper(*args):
                fn(*args)
                self.extend_timeout(delay, self.update_wallpapers)
            return wrapper

        def with_save(fn, delay=5):
            """Some signals should cause the configuration to be saved."""
            @wraps(fn)
            def wrapper(*args):
                fn(*args)
                self.set_timeout(delay, self.save_config)
            return wrapper

        def save_now():
            del self.timeout_callbacks[self.save_config]
            self.save_config()

        sig = self.ui.on_signal
        scrctrl = self.screen_controller
        sig(walliser.QUIT, self.interrupt)
        sig(walliser.SAVE, save_now)
        sig(walliser.UI_RESIZE, scrctrl.update_ui)
        sig(walliser.NEXT, with_interval_reset(scrctrl.next))
        sig(walliser.PREV, with_interval_reset(scrctrl.prev))
        sig(walliser.CYCLE_SCREENS, with_interval_reset(scrctrl.cycle_screens))
        sig(walliser.INCREASE_DELAY, self.increase_interval_delay)
        sig(walliser.REDUCE_DELAY, self.reduce_interval_delay)
        sig(walliser.NEXT_SCREEN, scrctrl.select_next)
        sig(walliser.PREV_SCREEN, scrctrl.select_prev)
        sig(walliser.TOGGLE_SCREEN, scrctrl.pause_unpause_selected)
        sig(walliser.NEXT_ON_SCREEN,
            with_interval_reset(scrctrl.next_on_selected))
        sig(walliser.PREV_ON_SCREEN,
            with_interval_reset(scrctrl.prev_on_selected))
        sig(walliser.INCREMENT_RATING,
            with_interval_delay(with_save(scrctrl.inc_rating_on_selected)))
        sig(walliser.DECREMENT_RATING,
            with_interval_delay(with_save(scrctrl.dec_rating_on_selected)))
        sig(walliser.INCREMENT_PURITY,
            with_interval_delay(with_save(scrctrl.inc_purity_on_selected)))
        sig(walliser.DECREMENT_PURITY,
            with_interval_delay(with_save(scrctrl.dec_purity_on_selected)))

    def update_wallpapers(self):
        self.screen_controller.next()
        self.set_timeout(self.interval_delay, self.update_wallpapers)

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

    def set_timeout(self, delay, fn):
        self.timeout_callbacks[fn] = time() + delay

    def extend_timeout(self, min_delay, fn):
        self.timeout_callbacks[fn] = max(
            self.timeout_callbacks[fn],
            time() + min_delay
        )

    def interrupt(self, *_):
        self.interrupted = True

    def run_event_loop(self):
        """Start processing Ui events."""
        self.interrupted = False
        while not self.interrupted:
            if not self.ui.process_keypress_listeners():
                # only do this when no input processing happened so
                # continuous input can be processed smoothly
                now = time()
                for fn, t in self.timeout_callbacks.copy().items():
                    if now > t:
                        del self.timeout_callbacks[fn]
                        fn()
