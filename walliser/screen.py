# -*- coding: utf-8 -*-

import subprocess

from .wallpaper import show_wallpapers
from .util import Observable, observed, steplist, modlist, each

def get_screen_count():
    """Finds out the number of connected screens."""
    # this is kind of a hack...
    return (
        subprocess
            .check_output(["xrandr", "-q"])
            .decode("ascii")
            .count(" connected ")
    )

class Screen(Observable):
    """Model representing one (usually physical) monitor"""

    @property
    def current_wallpaper(self):
        return self._wallpapers.current

    @property
    def is_current(self):
        return self._is_current

    @is_current.setter
    @observed
    def is_current(self, current):
        self._is_current = current

    @property
    def is_selected(self):
        return self._is_selected

    @is_selected.setter
    @observed
    def is_selected(self, selected):
        self._is_selected = selected

    @property
    def is_paused(self):
        return self._is_paused

    @is_paused.setter
    @observed
    def is_paused(self, paused):
        self._is_paused = paused

    __slots__ = ('idx', '_wallpapers',
                 '_is_current', '_is_selected', '_is_paused',
                )
    def __init__(self, idx, wallpapers,
                 is_current=False, is_selected=False, is_paused=False):
        super().__init__()
        self.idx = idx
        self._wallpapers = wallpapers
        self._is_current = is_current
        self._is_selected = is_selected
        self._is_paused = is_paused
        self.current_wallpaper.subscribe(self)

    def __repr__(self):
        return self.__class__.__name__ + ":" + str(self.idx)

    def __int__(self):
        return self.idx

    def __index__(self):
        return self.idx

    @observed
    def notify(self, *_):
        pass

    @observed
    def cycle_wallpaper(self, by):
        self._wallpapers.current.unsubscribe(self)
        self._wallpapers.cycle(by)
        self._wallpapers.current.show(self.idx)
        self._wallpapers.current.subscribe(self)

    def next_wallpaper(self):
        self.cycle_wallpaper(1)

    def prev_wallpaper(self):
        self.cycle_wallpaper(-1)

    @observed
    def notify(self, *_):
        pass


class ScreenController:
    """Manage available screens, cycling through them, pausing etc."""

    @property
    def selected_screen(self):
        """Return selected screen. If none is selected select current_screen."""
        return self.selectable_screens.current

    def __init__(self, ui, wallpaper_controller):
        self.ui = ui
        self.wallpaper_controller = wallpaper_controller

        self.screen_count = screen_count = get_screen_count()
        if not screen_count:
            raise Exception("No screens found.")
        self.ui.update_screen_count(screen_count)

        self.screens = []
        for idx in range(screen_count):
            wallpapers = modlist(steplist(self.wallpaper_controller.wallpapers,
                                          step=screen_count, offset=idx))
            screen = Screen(idx, wallpapers)
            screen.subscribe(ui)
            ui.update_screen(screen)
            self.screens.append(screen)

        self.active_screens = modlist(self.screens[:])
        self.active_screens.current.is_current = True

        self.selectable_screens = modlist(self.screens)
        self.selectable_screens.current.is_selected = True

    def update_ui(self, *_):
        """Update the moving parts of the UI that we can influence."""
        each(self.ui.update_screen, self.screens)

    def show_wallpapers(self):
        show_wallpapers(scr.current_wallpaper for scr in self.screens)

    def cycle_screens(self):
        """Shift entire screens array by one position."""
        self.selectable_screens.current.is_selected = False
        for screen in self.screens:
            screen.idx = (screen.idx + 1) % self.screen_count
        self.screens = self.screens[1:] + self.screens[0:1]
        self.selectable_screens = modlist(self.screens,
                                          self.selectable_screens.position)
        self.selectable_screens.current.is_selected = True
        self._update_active_screens()
        self.update_ui()
        self.show_wallpapers()

    def next(self):
        """Cycle forward in the global wallpaper rotation."""
        try:
            self.active_screens.current.is_current = False
            self.active_screens.next()
            self.active_screens.current.is_current = True
            self.active_screens.current.next_wallpaper()
        except IndexError:
            pass

    def prev(self):
        """Cycle backward in the global wallpaper rotation."""
        try:
            self.active_screens.current.prev_wallpaper()
            self.active_screens.current.is_current = False
            self.active_screens.prev()
            self.active_screens.current.is_current = True
        except IndexError:
            pass

    def select(self, scr):
        self.selectable_screens.current.is_selected = False
        self.selectable_screens.position = int(scr)
        self.selectable_screens.current.is_selected = True

    def select_next(self):
        self.select(self.selected_screen.idx + 1)

    def select_prev(self):
        self.select(self.selected_screen.idx - 1)

    def pause_selected(self):
        self.selected_screen.is_paused = True
        self._update_active_screens()

    def unpause_selected(self):
        self.selected_screen.is_paused = False
        self._update_active_screens()

    def pause_unpause_selected(self):
        self.selected_screen.is_paused = not self.selected_screen.is_paused
        self._update_active_screens()

    def _update_active_screens(self):
        """Regenerate the list of screens used in global wallpaper rotation."""
        try:
            self.active_screens.current.is_current = False
        except IndexError:
            pass
        self.active_screens = modlist(
            (s for s in self.screens if not s.is_paused),
            self.active_screens.position
        )
        try:
            self.active_screens.current.is_current = True
        except IndexError:
            pass
