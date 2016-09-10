# -*- coding: utf-8 -*-

from functools import wraps


def exhaust(iterator):
    """Do nothing with every element of an iterator."""
    for _ in iterator:
        pass

def each(function, *iterators):
    """Like map() but runs immediately and returns nothing."""
    exhaust(map(function, *iterators))


def dict_update_recursive(a, b):
    """Recursiveley merge dictionaries. Mutates first argument.
    """
    for key in b:
        if key in a and isinstance(a[key], dict) and isinstance(b[key], dict):
            dict_update_recursive(a[key], b[key])
        else:
            a[key] = b[key]


class modlist:
    """Like a list but keys cycle indefinitely over a sublist."""

    def __init__(self, base_list, step=1, offset=0):
        self._list = base_list
        self._len = len(base_list)
        self._step = step
        self._offset = offset

    def __bool__(self):
        return bool(self._list)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._list[(key * self._step + self._offset) % self._len]
        keys = range(
            key.start if key.start != None else 0,
            key.stop if key.stop != None else self._len,
            key.step if key.step != None else 1
        )
        return (self[i] for i in keys)

    def remove(self, item):
        self._list.remove(item)
        self._len -= 1


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
