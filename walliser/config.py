# -*- coding: utf-8 -*-

import os
import gzip
import json

def dict_update_recursive(a, b):
    """Recursiveley merge dictionaries. Mutates first argument."""
    for key in b:
        if key in a and isinstance(a[key], dict) and isinstance(b[key], dict):
            dict_update_recursive(a[key], b[key])
        else:
            a[key] = b[key]

def open_config_file(filename, mode="r"):
    """Open a file respecting .gz file endings."""
    if filename[-3:] == ".gz":
        return gzip.open(filename, mode, encoding="UTF-8")
    else:
        return open(filename, mode, encoding="UTF-8")


class Config(dict):
    """A dictionary that can read and write itself to a JSON file"""

    def __init__(self, filename, readonly=False):
        self.filename = filename
        self.readonly = readonly
        data = {}
        try:
            with open_config_file(filename, "rt") as config_file:
                data = json.load(config_file)
        except FileNotFoundError:
            pass
        except ValueError: # bad json
            # only raise if the file was not empty (i.e. actually malformed)
            if os.stat(self.filename).st_size != 0:
                raise
        if data:
            super().__init__(**data)

    def rec_update(self, data):
        """update recursively (only dicts, no other collection types)"""
        dict_update_recursive(self, data)

    def save(self):
        """Save current configuration into given file."""
        if self.readonly:
            return
        with open_config_file(self.filename, "wt") as config_file:
            json.dump(self, config_file, sort_keys=True, separators=(",", ":"))
