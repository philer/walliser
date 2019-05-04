# -*- coding: utf-8 -*-

import os
import shutil
import gzip
import json
import logging
from datetime import datetime
from pathlib import Path

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

def _open_config_file(path, mode="r"):
    """Open a file respecting .gz file endings."""
    if path[-3:] == ".gz":
        return gzip.open(path, mode, encoding="UTF-8")
    else:
        return open(path, mode, encoding="UTF-8")

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

    def __init__(self, path=None, readonly=False):
        if path:
            self._path = path
        elif 'WALLISER_CONFIG_FILE' in os.environ:
            self._path = Path(os.environ['WALLISER_CONFIG_FILE']).resolve()
        else:
            self._path = Path.home() / ".config/walliser/config.json"
        self._readonly = readonly
        self._data = self._load_data()

    def _load_data(self):
        try:
            with _open_config_file(self._path, "rt") as config_file:
                return json.load(config_file, object_hook=_deserialize)
        except FileNotFoundError:
            log.info("No config found at '%s'", self._path)
        except ValueError: # bad json
            # only raise if the file was not empty (i.e. actually malformed)
            if os.stat(self._path).st_size != 0:
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

        if self._path.is_file()
            # one backup per day keeps sorrow at bay
            backup = f"{self._path}.{datetime.now():%Y-%m-%d}.backup"
            if not os.path.isfile(backup):
                log.debug(f"Creating config backup '{backup}'")
                shutil.copyfile(self._path, backup)
        else:
            self._path.mkdir(parents=True, exist_ok=True)

        with _open_config_file(self._path, "wt") as config_file:
            json.dump(data, config_file, default=_serialize, separators=(",", ":"))
