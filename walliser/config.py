# -*- coding: utf-8 -*-

import os
import shutil
import gzip
import json
import logging
from datetime import datetime

log = logging.getLogger(__name__)

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

TIME_KEYS = {"added", "modified"}

def dict_update_recursive(a, b):
    """Recursiveley merge dictionaries. Mutates first argument."""
    for key in b:
        if key in a and isinstance(a[key], dict) and isinstance(b[key], dict):
            dict_update_recursive(a[key], b[key])
        else:
            a[key] = b[key]

def _open_config_file(filename, mode="r"):
    """Open a file respecting .gz file endings."""
    if filename[-3:] == ".gz":
        return gzip.open(filename, mode, encoding="UTF-8")
    else:
        return open(filename, mode, encoding="UTF-8")

def _serialize(obj):
    """Serialize things we know how to serialize."""
    return obj.strftime(TIME_FORMAT)

def _deserialize(obj):
    for key in TIME_KEYS:
        try:
            obj[key] = datetime.strptime(obj[key], TIME_FORMAT)
        except KeyError:
            pass
    return obj


class Config:
    """A dictionary that can read and write itself to a JSON file"""

    @property
    def readonly(self):
        return self._readonly

    @readonly.setter
    def readonly(self, yes):
        if not yes:
            raise ValueError("Can not disable readonly on config after initialization.")
        self._readonly = True

    def __init__(self, filename=None, readonly=False):
        if filename:
            self._filename = filename
        elif 'WALLISER_CONFIG_FILE' in os.environ:
            self._filename = os.environ['WALLISER_CONFIG_FILE']
        else:
            self._filename = os.environ['HOME'] + "/.walliser.json"
        self._readonly = readonly
        self._data = self._load_data()

    def _load_data(self):
        try:
            with _open_config_file(self._filename, "rt") as config_file:
                return json.load(config_file, object_hook=_deserialize)
        except FileNotFoundError:
            log.info("No config found at '%s'", self._filename)
        except ValueError: # bad json
            # only raise if the file was not empty (i.e. actually malformed)
            if os.stat(self._filename).st_size != 0:
                raise
        return {"modified": datetime.min, "wallpapers": {}}

    def __getitem__(self, key):
        return self._data[key]

    def rec_update(self, data):
        """update recursively (only dicts, no other collection types)"""
        dict_update_recursive(self._data, data)

    def save(self):
        """Save current configuration into given file."""
        if self.readonly:
            return
        data = self._load_data()
        if data["modified"] > self._data["modified"]:
            log.info("Config has been outdated since startup.")
            dict_update_recursive(data, self._data)
        else:
            data = self._data
        data["modified"] = self._data["modified"] = datetime.now()

        # one backup per day keeps sorrow at bay
        backup = self._filename + f".{datetime.now():%Y-%m-%d}.backup"
        if os.path.isfile(self._filename) and not os.path.isfile(backup):
            log.info(f"Creating config backup '{backup}'")
            shutil.copyfile(self._filename, backup)

        with _open_config_file(self._filename, "wt") as config_file:
            json.dump(data, config_file, default=_serialize, separators=(",", ":"))
