from setuptools import setup

setup(
    name='walliser',
    description='Interactive commandline tool for cycling through wallpapers.',
    version='0.1',
    license='MIT',
    author='Philipp Miller',
    author_email='me@philer.org',
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
    ],
    entry_points = {
        'console_scripts': ['walliser = walliser.cli:main'],
    }
)