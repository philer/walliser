# -*- coding: utf-8 -*-

import signal

from .util import get_file_hash, info, warning, error, die, progress_bar
from .config import Config


def find_duplicates(config):
    """Check for file duplicates in config"""

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

    if updated_wallpapers:
        info("saving " + str(len(updated_wallpapers)) + " updates…")
        config.update({
            "wallpapers": {
                path: wallpapers[path] for path in updated_wallpapers
            },
        })
        config.save()
        info("done")


def interrupt_signal_handler(signal, frame):
    die("Interrupted, exiting now!")
