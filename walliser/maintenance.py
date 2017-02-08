# -*- coding: utf-8 -*-

import signal

from .util import get_file_hash, info, warning, error, die, progress_bar
from .config import Config

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

def find_duplicates(config):
    """Check for file duplicates in config, add hashes"""
    wallpapers = config["wallpapers"]
    updated_wallpapers = set()
    hashes = dict()
    dupes = set()

    signal.signal(signal.SIGINT, interrupt_signal_handler)
    info("Comparing hashes of " + str(len(wallpapers)) + " wallpapers…")
    bar = progress_bar(len(wallpapers))
    for path, data in sorted(wallpapers.items()):
        bar(after=str(len(dupes)) + " duplicates found. "
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


def interrupt_signal_handler(signal, frame):
    die("Interrupted, exiting now!")
