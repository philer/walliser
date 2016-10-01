# -*- coding: utf-8 -*-

import os

import gzip
import json

from .util import dict_update_recursive

class Config:

    def __init__(self, filename):
        self._filename = filename
        self._unsaved = {}

    def __getitem__(self, key):
        """Return config as nested dict including unsaved changes.
        Optional key allows accessing nested properties like
            "key.subkey.subsubkey"
        """
        config = self.load()
        if self._unsaved:
            config = dict_update_recursive(config, self._unsaved)
        if key:
            for subkey in key.split("."):
                config = config[subkey]
        return config

    def load(self):
        """Return config as nested dict directly from file"""
        if self._filename:
            try:
                with self.open_config_file(self._filename, "rt") as config_file:
                    return json.load(config_file)
            except FileNotFoundError:
                pass
            except ValueError: # bad json
                # only raise if the file was not empty (really "malformed")
                if os.stat(self._filename).st_size != 0:
                    raise
        return {}

    def update(self, data):
        dict_update_recursive(self._unsaved, data)

    def save(self, pretty="auto"):
        """Save current configuration into given file."""
        if not self._unsaved or not self._filename:
            return False

        config = self.load()
        dict_update_recursive(config, self._unsaved)

        with self.open_config_file(self._filename, "wt") as config_file:

            if pretty == True or (
                    pretty == "auto" and self._filename[-3:] != ".gz"):
                json.dump(config, config_file,
                    sort_keys=True, indent="\t")
            else:
                json.dump(config, config_file,
                    sort_keys=False, separators=(",", ":"))

        return True

    @staticmethod
    def open_config_file(filename, mode="r"):
        """Open a I/O of JSON data, respecting .gz file endings."""
        if filename[-3:] == ".gz":
            return gzip.open(filename, mode, encoding="UTF-8")
        else:
            return open(filename, mode, encoding="UTF-8")
