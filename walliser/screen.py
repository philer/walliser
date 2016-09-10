# -*- coding: utf-8 -*-

import subprocess

from .util import Observable, observed, modlist, each

class Screen(Observable):
    """Model representing one (usually physical) monitor"""

    @property
    def current_wallpaper(self):
        return self.wallpapers[self._current_wallpaper_offset]

    @property
    def current(self):
        return self._current

    @current.setter
    @observed
    def current(self, current):
        self._current = current

    @property
    def selected(self):
        return self._selected

    @selected.setter
    @observed
    def selected(self, selected):
        self._selected = selected

    @property
    def paused(self):
        return self._paused

    @paused.setter
    @observed
    def paused(self, paused):
        self._paused = paused

    def __init__(self, ui, idx, wallpapers,
            current=False, selected=False, paused=False):
        self.ui = ui
        self.idx = idx
        self.wallpapers = wallpapers
        self._current_wallpaper_offset = 0
        self._current = current
        self._selected = selected
        self._paused = paused

        Observable.__init__(self)
        self.subscribe(ui.update_screen, self)
        self.current_wallpaper.subscribe(ui.update_screen, self)
        ui.update_screen(self)

    def __repr__(self):
        return "screen:" + str(self.idx)

    @observed
    def cycle_wallpaper(self, offset):
        self.current_wallpaper.unsubscribe(self.ui.update_screen)
        self._current_wallpaper_offset += offset
        self.current_wallpaper.subscribe(self.ui.update_screen, self)

    def next_wallpaper(self):
        self.cycle_wallpaper(1)

    def prev_wallpaper(self):
        self.cycle_wallpaper(-1)


class ScreenController:
    """Manage available screens, cycling through them, pausing etc."""

    @property
    def current_screen(self):
        """Returns last (automatically) updated screen."""
        if self.active_screens:
            return self.active_screens[self._current_screen_offset]

    @property
    def selected_screen(self):
        """Return selected screen. If none is selected select current_screen."""
        return self._selected_screen

    @selected_screen.setter
    def selected_screen(self, selected_screen):
        """Return selected screen. If none is selected select current_screen."""
        self._selected_screen.selected = False
        self._selected_screen = selected_screen
        self._selected_screen.selected = True

    def __init__(self, ui, wallpaper_controller):
        self.ui = ui
        self.wallpaper_controller = wallpaper_controller

        screen_count = self._get_screen_count()
        if not screen_count:
            raise Exception("No screens found.")
        self.screen_count = screen_count
        self.ui.update_screen_count(screen_count)
        self.screens = []
        for idx in range(screen_count):
            wallpapers = modlist(
                self.wallpaper_controller.wallpapers,
                screen_count,
                idx)
            self.screens.append(Screen(self.ui, idx, wallpapers))

        self.active_screens = modlist(self.screens[:])
        self._current_screen_offset = 0
        self.current_screen.current = True
        self._selected_screen = self.screens[0]
        self._selected_screen.selected = True
        # self.update_live_screens()
        # self.run()

    def _get_screen_count(self):
        """Finds out the number of connected screens."""
        # this is kind of a hack...
        return (
            subprocess
            .check_output(["xrandr", "-q"])
            .decode("ascii")
            .count(" connected ")
        )

    def update_ui(self, *_):
        """Update the moving parts of the UI that we can influence."""
        each(self.ui.update_screen, self.screens)

    def update_live_screens(self):
        """Get each screen's current wallpaper and put them on the monitors."""
        self.wallpaper_controller.update_live_wallpapers(
            scr.current_wallpaper for scr in self.screens
        )

    def cycle_screens(self):
        """Shift entire screens array by one position."""
        for screen in self.screens:
            screen.idx = (screen.idx + 1) % self.screen_count
        self.screens = self.screens[1:] + self.screens[0:1]
        self._update_active_screens()
        self.select_prev()
        self.update_ui()
        self.update_live_screens()

    def next(self):
        """Cycle forward in the global wallpaper rotation."""
        current = self.current_screen
        if current:
            current.current = False
            self._current_screen_offset += 1
            self.current_screen.current = True
            self.current_screen.next_wallpaper()
            self.update_live_screens()

    def prev(self):
        """Cycle backward in the global wallpaper rotation."""
        current = self.current_screen
        if current:
            current.prev_wallpaper()
            self.current_screen.current = False
            self._current_screen_offset -= 1
            self.current_screen.current = True
            self.update_live_screens()

    def select(self, scr):
        """Flexible input setter for selected_screen"""
        if isinstance(scr, Screen):
            idx = scr.idx
        elif isinstance(scr, int):
            idx = scr
        elif isinstance(scr, str):
            idx = int(scr) - 1
        else:
            raise TypeError()
        # We rely on the @property setter
        self.selected_screen = self.screens[idx]

    def select_next(self):
        """Advance the selected screen to the next of all screens."""
        # We rely on the @property getter/setter
        idx = self.selected_screen.idx
        self.selected_screen = self.screens[(idx + 1) % self.screen_count]

    def select_prev(self):
        """Advance the selected screen to the next of all screens."""
        # We rely on the @property getter/setter
        idx = self.selected_screen.idx
        self.selected_screen = self.screens[(idx - 1) % self.screen_count]

    def pause_selected(self):
        self.selected_screen.paused = True
        self._update_active_screens()

    def unpause_selected(self):
        self.selected_screen.paused = False
        self._update_active_screens()

    def pause_unpause_selected(self):
        self.selected_screen.paused = not self.selected_screen.paused
        self._update_active_screens()

    def _update_active_screens(self):
        """Regenerate the list of screens used in global wallpaper rotation."""
        if self.current_screen:
            self.current_screen.current = False
        active_screens = [s for s in self.screens if not s.paused]
        if active_screens:
            self.active_screens = modlist(active_screens)
            self.current_screen.current = True
            # self.update_interval.start() # TODO remove
        else:
            self.active_screens = []
            # self.update_interval.stop() # TODO remove

    def next_on_selected(self):
        """Update selected (or current) screen to the next wallpaper."""
        self.selected_screen.next_wallpaper()
        self.update_live_screens()

    def prev_on_selected(self):
        """Update selected (or current) screen to the previous wallpaper."""
        self.selected_screen.prev_wallpaper()
        self.update_live_screens()

    def inc_rating_on_selected(self):
        """Increment rating of current wallpaper on selected screen."""
        self.selected_screen.current_wallpaper.rating += 1

    def dec_rating_on_selected(self):
        """Decrement rating of current wallpaper on selected screen."""
        self.selected_screen.current_wallpaper.rating -= 1

    def inc_purity_on_selected(self):
        """Increment purity of current wallpaper on selected screen."""
        self.selected_screen.current_wallpaper.purity += 1

    def dec_purity_on_selected(self):
        """Decrement purity of current wallpaper on selected screen."""
        self.selected_screen.current_wallpaper.purity -= 1