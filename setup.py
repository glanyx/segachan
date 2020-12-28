#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages
from sweeperbot._version import __version__

with open("README.rst") as readme_file:
    readme = readme_file.read()

with open("HISTORY.rst") as history_file:
    history = history_file.read()

setup(
    name="sweeperbot",
    version=__version__,
    description="Test",
    long_description=readme + "\n\n" + history,
    author="Glanyx",
    author_email="mikekornet@live.co.uk",
    url="https://github.com/glanyx/segachan/",
    entry_points={"console_scripts": ["sweeperbot=sweeperbot.launch:main"]},
    include_package_data=True,
    license="GNU General Public License v3",
    zip_safe=False,
    keywords=[
        "sweeperbot",
        "sweeper",
        "bot",
        "discord",
        "benedict",
        "benedict 9940",
        "segachan",
    ],
    classifiers=[
        "Development Status :: 2- Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
    ],
)
