import configparser
import logging.config
import sys
import time
from base64 import b64decode
from os.path import abspath, dirname, join

import discord
from layer7_utilities import LoggerConfig

from sweeperbot._version import __version__
from sweeperbot.bot import Bot
from sweeperbot.constants import __botname__

curdir = join(abspath(dirname(__file__)))
parentdir = join(curdir, "../")

botconfig = configparser.ConfigParser()
botconfig.read(join(parentdir, "botconfig.ini"))
# The Discord Token is a combination of a base 64 of user ID, timestamp, and crypto key.
# See here: https://imgur.com/7WdehGn
__token__ = botconfig.get("BotConfig", "DISCORDTOKEN")
tmp_token_split = __token__.split(".")
userid = int(b64decode(tmp_token_split[0]))


def setup_logger():
    # Create the logger
    # Try and get the logs path from the config file. If not set then use the packages internal default
    try:
        LOGSPATH = botconfig.get("Misc", "LOGSPATH")
        loggerconfig = LoggerConfig(
            __dsn__=None,
            __app_name__=f"{__botname__}_{userid}",
            __version__=__version__,
            logspath=LOGSPATH,
            raven=False,
        )
    except Exception:
        loggerconfig = LoggerConfig(
            __dsn__=None,
            __app_name__=f"{__botname__}_{userid}",
            __version__=__version__,
            raven=False,
        )
    logging.config.dictConfig(loggerconfig.get_config())
    return logging.getLogger("root")


def main():
    try:
        log = setup_logger()
        bot = Bot(log)
        bot.run()
    except discord.errors.LoginFailure as err:
        print(f"Exception logging in. {err}")
        time.sleep(150)
    except KeyboardInterrupt:
        print("Caught Keyboard Interrupt")
        sys.exit()


if __name__ == "__main__":
    main()
