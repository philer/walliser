# -*- coding: utf-8 -*-

from functools import wraps
from urllib.parse import quote as urlquote


def observed(method):
    """Decorator to be added on methods that should notify observers
    after they were executed."""
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        method(self, *args, **kwargs)
        self._notify_observers()
    return wrapper


class Observable:
    """An observable object calls registered callbacks whenever one of its
    @observed methods (including @property setters) is called.
    """

    def __init__(self):
        self._observers = dict()

    def subscribe(self, callback, *args):
        """Add a subscriber to this object's observer list"""
        self._observers[callback] = args

    def unsubscribe(self, callback):
        """Remove a subscriber from this object's observer list"""
        del self._observers[callback]

    def _notify_observers(self):
        for observer, args in self._observers.items():
            observer(*args)


class Wallpaper(Observable):
    """Model representing one wallpaper"""

    @property
    def as_dict(self):
        """Dictionary representation of this object for storing.
        Excludes path so it can be used as key.
        """
        return {
            # "path": self.path,
            "width": self.width,
            "height": self.height,
            "format": self.format,
            "rating": self.rating,
            "purity": self.purity,
        }

    @property
    def url(self):
        return "file://" + urlquote(self.path)

    @property
    def rating(self):
        return self._rating

    @rating.setter
    @observed
    def rating(self, rating):
        self._rating = rating

    @property
    def purity(self):
        return self._purity

    @purity.setter
    @observed
    def purity(self, purity):
        self._purity = purity

    def __init__(self, path, width, height, format, rating, purity):
        Observable.__init__(self)
        self.path = path
        self.width = width
        self.height = height
        self.format = format
        self.rating = rating
        self.purity = purity
        # (self.path, self.width, self.height, self.format) = filedata

    def __repr__(self):
        return self.path

    def __eq__(self, other):
        return self.path == other.path

    def __hash__(self, other):
        return hash(Wallpaper) ^ hash(self.path)


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
