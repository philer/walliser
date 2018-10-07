# -*- coding: utf-8 -*-

import os

from .util import get_file_hash
from .progress import progress
from .wallpaper import WallpaperController

import logging
from signal import signal, SIGINT, SIGPIPE, SIG_DFL

log = logging.getLogger(__name__)

def interrupt_signal_handler(signal, frame):
    print("Interrupted, exiting now!")
    sys.exit(1)
signal(SIGINT, interrupt_signal_handler)
signal(SIGPIPE, SIG_DFL)  # ignore end of pipe (e.g. ...|head )


def run(config):
    find_invalid_paths(config)

def find_invalid_paths(wpctrl):
    dead_count = 0
    for wp in progress(wpctrl.wallpapers, text="{0.hash} ({0.path})"):
        wp.check_paths()
        if wp.path is None:
            dead_count += 1
    log.info("checked a total of %s wallpapers", len(wpctrl.wallpapers))
    log.info("%s wallpapers have no path left", dead_count)
    wpctrl.save_updates()




# OBSOLETE
def check_dead_paths(config):
    """List paths that no longer point to files."""
    wallpapers = config["wallpapers"]
    for i, (hash, wp_data) in enumerate(progress(wallpapers.items(), text="{0[1][paths][0]}")):
        for path in wp_data["paths"]:
            if not os.path.isfile(path):
                warning("path '{}' doesn't exist.".format(path))


# OBSOLETE
def convert_to_hash_keys(config):
    """Restructure config.wallpapers to use hashes as keys instead of paths"""
    by_paths = config["wallpapers"]
    by_hashes = dict()
    for path, data in by_paths.items():
        hash = data["hash"]
        if hash in by_hashes:
            duplicate = by_hashes[hash]
            duplicate["paths"].append(path)
            duplicate["paths"].sort()
            if (duplicate["purity"] != data["purity"]
                    or duplicate["rating"] != data["rating"]):
            #     if duplicate["rating"] == 0 == duplicate["purity"]:
            #         duplicate["rating"] = data["rating"]
            #         duplicate["purity"] = data["purity"]
            #     elif not data["rating"] == 0 == data["purity"]:
                    print("Settings for file://" + path + " differ:")
            #         for key in ["purity", "rating"]:
            #             if duplicate[key] != data[key]:
            #                 msg = "{}: {} or {}? Enter a value > ".format(
            #                         key, duplicate[key], data[key])
            #                 duplicate[key] = type(duplicate[key])(input(msg))
            duplicate["purity"] = min(duplicate["purity"],data["purity"])
            duplicate["rating"] = max(duplicate["rating"],data["rating"])
        else:
            del data["hash"]
            data["paths"] = [path]
            by_hashes[hash] = data
    config["wallpapers"] = by_hashes
    config.save()


# OBSOLETE
def find_duplicates(config):
    """Check for file duplicates in config, add hashes"""
    wallpapers = config["wallpapers"]
    updated_wallpapers = set()
    hashes = dict()
    dupes = set()

    info("Comparing hashes of " + str(len(wallpapers)) + " wallpapers…")
    bar = smooth_bar(len(wallpapers))
    for path, data in sorted(wallpapers.items()):
        bar(text=str(len(dupes)) + " duplicates found. "
                 + str(len(updated_wallpapers)) + " new hashes calculated – "
                 + path)
        try:
            hash = data["hash"]
        except KeyError:
            hash = get_file_hash(path)
            data["hash"] = hash
            updated_wallpapers.add(path)

        if hash in hashes:
            # warning("Hash collision for {} ({})".format(path, hash))
            hashes[hash].append(path)
            dupes.add(hash)
        else:
            hashes[hash] = [path]

    info("found " + str(len(dupes)) + " duplicates")
    for hash in dupes:
        info("hash: " + hash)
        for path in hashes[hash]:
            data = wallpapers[path]
            info("(rating: {rating:>2}, purity: {purity:>2}) – ".format(**data) + path)

    if updated_wallpapers and input("Save " + str(len(updated_wallpapers)) + " updates? (y/N)") == 'y':
        info("saving " + str(len(updated_wallpapers)) + " updates…")
        config.rec_update({
            "wallpapers": {
                path: wallpapers[path] for path in updated_wallpapers
            },
        })
        config.save()
        info("done")

