import configparser
from os.path import abspath, dirname, join

curdir = join(abspath(dirname(__file__)))
parentdir = join(curdir, "../")

botconfig = configparser.ConfigParser()
botconfig.read(join(parentdir, "botconfig.ini"))

VERSION_MAJOR = botconfig.get("BotConfig", "VERSION_MAJOR")
VERSION_MINOR = botconfig.get("BotConfig", "VERSION_MINOR")
VERSION_PATCH = botconfig.get("BotConfig", "VERSION_PATCH")


__version_info__ = (VERSION_MAJOR, VERSION_MINOR, VERSION_PATCH)
__version__ = ".".join(map(str, __version_info__))
