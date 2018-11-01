# -*- coding: utf-8 -*-

import subprocess
import logging
import re

from .wallpaper import show_wallpapers
from .util import Observable, observed, steplist, modlist, each

log = logging.getLogger(__name__)

def get_screens_data():
    """Iterate data of all active screens by parsing `xrandr --query`."""
    result = subprocess.run(("xrandr", "--query"),
                            check=True, universal_newlines=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    # kinda like sscanf
    props = (('output', str), ('primary', bool), ('width', int), ('height', int))
    regex = re.compile(r"^(\S+) connected( primary)? (\d+)x(\d+)",
                       flags=re.MULTILINE | re.ASCII)
    for match in regex.findall(result.stdout):
        yield {name: type(value) for (name, type), value in zip(props, match)}


class Screen(Observable):
    """Model representing one (usually physical) monitor"""

    @property
    def current_wallpaper(self):
        return self._wallpapers.current

    @property
    def current_wallpaper_scale(self):
        wp = self._wallpapers.current
        return wp.scale * max(self.width / wp.width, self.height / wp.height)

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

    def __init__(self, idx, wallpapers,
                 is_current=False, is_selected=False, is_paused=False,
                 **props):
        self.idx = idx
        self._wallpapers = modlist(wallpapers)
        self._is_current = is_current
        self._is_selected = is_selected
        self._is_paused = is_paused
        for attr, value in props.items():
            setattr(self, attr, value)
        super().__init__()
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


class ScreenController:
    """Manage available screens, cycling through them, pausing etc."""

    @property
    def selected_screen(self):
        """Return selected screen. If none is selected select current_screen."""
        return self.selectable_screens.current

    def __init__(self, ui, wallpapers):
        self.ui = ui

        screens_data = tuple(get_screens_data())
        if not screens_data:
            raise Exception("No screens found.")

        screen_count = len(screens_data)
        log.debug("Found %d screens.", screen_count)
        self.ui.update_screen_count(screen_count)

        self.screens = []
        for idx, data in enumerate(screens_data):
            wps = steplist(wallpapers, step=screen_count, offset=idx)
            log.debug("Initializing screen %d with %d wallpapers and properties %s",
                      idx, len(wps), data)
            screen = Screen(idx, wps, **data, is_paused=True)
            screen.subscribe(ui)
            ui.update_screen(screen)
            self.screens.append(screen)

        self.active_screens = modlist(self.screens[:])
        self.active_screens.current.is_current = True

        self.selectable_screens = modlist(self.screens)
        self.selectable_screens.current.is_selected = True

        self._update_active_screens()

    def update_ui(self, *_):
        """Update the moving parts of the UI that we can influence."""
        each(self.ui.update_screen, self.screens)

    def show_wallpapers(self):
        show_wallpapers(scr.current_wallpaper for scr in self.screens)

    def cycle_screens(self):
        """Shift entire screens array by one position."""
        self.selectable_screens.current.is_selected = False
        for screen in self.screens:
            screen.idx = (screen.idx + 1) % len(self.screens)
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
        except IndexError: # no active screens left
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
            [s for s in self.screens if not s.is_paused],
            self.active_screens.position
        )
        try:
            self.active_screens.current.is_current = True
        except IndexError:
            pass
