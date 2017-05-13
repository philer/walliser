from setuptools import setup

from walliser import (__version__,
                      __license__,
                      __author__,
                      __email__,
                      __copyright__)

setup(
    name='walliser',
    description='Interactive commandline tool for cycling through wallpapers.',
    version=__version__,
    license=__license__,
    author=__author__,
    author_email=__email__,
    url='nowhere yet',
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Development Status :: 3 - Alpha',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.4',
        'Environment :: Console :: Curses',
        'Operating System :: POSIX :: Linux',
        'Topic :: Desktop Environment',
        'Topic :: Utilities',
        'Natural Language :: English',
    ],
    packages=['walliser'],
    install_requires=[
        'pillow',
        'docopt',
    ],
    entry_points = {
        'console_scripts': ['walliser = walliser.cli:main'],
    }
)
