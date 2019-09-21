walliser
========

**Interactive commandline tool for cycling through wallpapers**

Example
-------

Cycle through wallpapers from multiple locations in random order
~$ walliser pictures/wallpapers/ pictures/more/wallpapers pictures/image.jpg

Store files in a config file and reuse them later
~$ walliser -c ~/.walliser.json pictures/wallpapers
~$ walliser -c ~/.walliser.json

Usage
-----
usage: walliser [-h] [-c CONFIG_FILE] [-i N] [-s | -S] [-r MIN_RATING]
                [-R MAX_RATING] [-p MIN_PURITY] [-P MAX_PURITY]
                [FILE/DIR [FILE/DIR ...]]

Update desktop background periodically

positional arguments:
  FILE/DIR              Any number of files or directories where wallpapers
                        can be found. Supports globbing

optional arguments:
  -h, --help            show this help message and exit
  -c CONFIG_FILE, --config-file CONFIG_FILE
                        Read and store wallpaper data in this file. JSON
                        formatted.
  -i N, --interval N    Seconds between updates (may be float)
  -s, --shuffle         Cycle through wallpapers in random order.
  -S, --sort            Cycle through wallpapers in alphabetical order (fully
                        resolved path).
  -r MIN_RATING, --min-rating MIN_RATING
                        Filter wallpapers by minimum rating
  -R MAX_RATING, --max-rating MAX_RATING
                        Filter wallpapers by maximum rating
  -p MIN_PURITY, --min-purity MIN_PURITY
                        Filter wallpapers by maximum rating
  -P MAX_PURITY, --max-purity MAX_PURITY
                        Filter wallpapers by minimum rating
