# -*- coding: utf-8 -*-

from functools import wraps
from time import time
from enum import Enum, unique
from inspect import signature
import logging
import signal

from .screen import ScreenController
from .util import AutoStrEnumMeta

log = logging.getLogger(__name__)

@unique
class Signal(str, Enum, metaclass=AutoStrEnumMeta):
    QUIT
    SAVE

    UI_RESIZE

    NEXT, PREV
    INCREASE_DELAY, REDUCE_DELAY

    NEXT_SCREEN, PREV_SCREEN
    TOGGLE_SCREEN
    CYCLE_SCREENS

    NEXT_ON_SCREEN, PREV_ON_SCREEN

    INCREMENT_RATING, DECREMENT_RATING
    INCREMENT_PURITY, DECREMENT_PURITY

    TOGGLE_TAG

    MOVE_LEFT, MOVE_DOWN, MOVE_UP, MOVE_RIGHT
    ZOOM_IN, ZOOM_OUT, ZOOM_FULL, RESET_ZOOM

    def __init__(self, _):
        self._subscribers = {}

    def subscribe(self, fn):
        self._subscribers[fn] = signature(fn).parameters.keys()

    def unsubscribe(self, fn):
        del self._subscribers[fn]

    def trigger(self, **kwargs):
        kwargs['signal'] = self
        for fn, argnames in self._subscribers.items():
            fn(**{arg: kwargs[arg] for arg in argnames if arg in kwargs})


class Core:
    """Main entry point to the application, manages signals and main loop."""

    @property
    def selected_screen(self):
        return self.screen_controller.selected_screen

    @property
    def selected_wallpaper(self):
        return self.selected_screen.current_wallpaper

    def __init__(self, ui, config, wallpapers, interval=5.0):
        self.ui = ui
        self.config = config
        self.wallpapers = wallpapers

        self.timeout_callbacks = {}
        self.interval = interval
        self.ui.update_interval(interval)

        with self.ui:
            self.screen_controller = ScreenController(ui, self.wallpapers)
            self.screen_controller.show_wallpapers()

            signal.signal(signal.SIGINT, self.interrupt)
            self.assign_ui_listeners()
            self.set_timeout(self.interval, self.update_wallpapers)
            self.set_timeout(2, self.save_config)
            self.run_event_loop()

        self.save_config()

    def save_config(self):
        self.clear_timeout(self.save_config)
        self.wallpapers.save_updates()

    def assign_ui_listeners(self):
        """Set up Ui interaction listeners."""

        def with_interval_reset(fn):
            """Some signals should reset the pending rotation timeout."""
            @wraps(fn)
            def wrapper(*args):
                fn(*args)
                self.set_timeout(self.interval, self.update_wallpapers)
            return wrapper

        scrctrl = self.screen_controller
        Signal.QUIT.subscribe(self.interrupt)
        Signal.SAVE.subscribe(self.save_config)
        Signal.UI_RESIZE.subscribe(scrctrl.update_ui)
        Signal.NEXT.subscribe(with_interval_reset(scrctrl.next))
        Signal.PREV.subscribe(with_interval_reset(scrctrl.prev))
        Signal.CYCLE_SCREENS.subscribe(with_interval_reset(scrctrl.cycle_screens))
        Signal.INCREASE_DELAY.subscribe(self.increase_interval)
        Signal.REDUCE_DELAY.subscribe(self.reduce_interval)
        Signal.NEXT_SCREEN.subscribe(scrctrl.select_next)
        Signal.PREV_SCREEN.subscribe(scrctrl.select_prev)
        Signal.TOGGLE_SCREEN.subscribe(scrctrl.pause_unpause_selected)

        @Signal.NEXT_ON_SCREEN.subscribe
        def next_on_selected():
            """Update selected (or current) screen to the next wallpaper."""
            self.selected_screen.next_wallpaper()
            self.set_timeout(self.interval, self.update_wallpapers)

        @Signal.PREV_ON_SCREEN.subscribe
        def prev_on_selected():
            """Update selected (or current) screen to the previous wallpaper."""
            self.selected_screen.prev_wallpaper()
            self.set_timeout(self.interval, self.update_wallpapers)

        @Signal.INCREMENT_RATING.subscribe
        def inc_rating():
            self.selected_wallpaper.rating += 1
            self.extend_timeout(3, self.update_wallpapers)
            self.set_timeout(10, self.save_config)

        @Signal.DECREMENT_RATING.subscribe
        def dec_rating():
            self.selected_wallpaper.rating -= 1
            self.extend_timeout(3, self.update_wallpapers)
            self.set_timeout(10, self.save_config)

        @Signal.INCREMENT_PURITY.subscribe
        def inc_purity():
            self.selected_wallpaper.purity += 1
            self.extend_timeout(3, self.update_wallpapers)
            self.set_timeout(10, self.save_config)

        @Signal.DECREMENT_PURITY.subscribe
        def dec_purity():
            self.selected_wallpaper.purity -= 1
            self.extend_timeout(3, self.update_wallpapers)
            self.set_timeout(10, self.save_config)

        @Signal.TOGGLE_TAG.subscribe
        def toggle_tag():
            tags = self.ui.input("tags: ")
            for tag in filter(None, map(str.strip, tags.split(','))):
                self.selected_wallpaper.toggle_tag(tag)
                self.set_timeout(10, self.save_config)
            self.extend_timeout(3, self.update_wallpapers)

        @Signal.MOVE_UP.subscribe
        def move_up():
            self.selected_wallpaper.y_offset += 10
            scrctrl.show_wallpapers()

        @Signal.MOVE_DOWN.subscribe
        def move_down():
            self.selected_wallpaper.y_offset -= 10
            scrctrl.show_wallpapers()

        @Signal.MOVE_LEFT.subscribe
        def move_left():
            self.selected_wallpaper.x_offset += 10
            scrctrl.show_wallpapers()

        @Signal.MOVE_RIGHT.subscribe
        def move_right():
            self.selected_wallpaper.x_offset -= 10
            scrctrl.show_wallpapers()

        @Signal.ZOOM_IN.subscribe
        def zoom_in():
            self.selected_wallpaper.scale += .05
            scrctrl.show_wallpapers()

        @Signal.ZOOM_OUT.subscribe
        def zoom_out():
            self.selected_wallpaper.scale -= .05
            scrctrl.show_wallpapers()

        @Signal.ZOOM_FULL.subscribe
        def zoom_full():
            wp, scr = self.selected_wallpaper, self.selected_screen
            wp.scale = 1 / max(scr.width / wp.width, scr.height / wp.height)
            scrctrl.show_wallpapers()

        @Signal.RESET_ZOOM.subscribe
        def reset_zoom():
            self.selected_wallpaper.scale = 1
            self.selected_wallpaper.x_offset = 0
            self.selected_wallpaper.y_offset = 0
            scrctrl.show_wallpapers()

    def update_wallpapers(self):
        self.screen_controller.next()
        self.set_timeout(self.interval, self.update_wallpapers)

    def increase_interval(self):
        """Reduce wallpaper rotation speed by a quarter second."""
        # self.interval *= 1.1
        self.interval += 0.25
        self.ui.update_interval(self.interval)

    def reduce_interval(self):
        """Increase wallpaper rotation speed by a quarter second."""
        # self.interval *= 1/1.1
        self.interval -= 0.25
        self.ui.update_interval(self.interval)

    def set_timeout(self, delay, fn):
        self.timeout_callbacks[fn] = time() + delay

    def clear_timeout(self, fn):
        try:
            del self.timeout_callbacks[fn]
        except KeyError:
            pass

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
                        self.clear_timeout(fn)
                        fn()
