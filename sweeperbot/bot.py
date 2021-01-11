import configparser
import sys
from datetime import datetime
from os.path import abspath, dirname, join

import aiohttp
import discord
import sentry_sdk
from discord.ext import commands
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from sweeperbot._version import __version__
from sweeperbot.cogs.utils import prompt
from sweeperbot.constants import Constants, __botname__, __description__
from sweeperbot.db.manager import DatabaseManager
from sweeperbot.utilities.antispam import AntiSpam
from sweeperbot.utilities.helpers import Helpers
from sweeperbot.utilities.role_assignment import RoleAssignment
from sweeperbot.utilities.tasks import Tasks

from sweeperbot.cogs.utils import checks

# from sweeperbot.cogs.utils.imgur_api import ImgurAPI

curdir = join(abspath(dirname(__file__)))
parentdir = join(curdir, "../")

botconfig = configparser.ConfigParser()
botconfig.read(join(parentdir, "botconfig.ini"))

__dsn__ = botconfig.get("BotConfig", "DSN")
__token__ = botconfig.get("BotConfig", "DISCORDTOKEN")
try:
    __environment__ = botconfig.get("BotConfig", "ENVIRONMENT")
except Exception:
    __environment__ = "Development"

initial_extensions = (
    # Mod commands
    "cogs.modtools.warn",
    "cogs.modtools.ban",
    "cogs.modtools.kick",
    "cogs.modtools.alert",
    "cogs.modtools.vote",
    "cogs.modtools.say",
    "cogs.modtools.allroles",
    "cogs.modtools.mute",
    "cogs.modtools.note",
    "cogs.modtools.history",
    "cogs.modtools.role",
    "cogs.modtools.send",
    "cogs.modtools.purge",
    "cogs.modtools.server",
    "cogs.modtools.rra_role_assignment",
    "cogs.modtools.blacklist",
    "cogs.modtools.list_requests",
    "cogs.modtools.close_request",
    # Misc commands
    "cogs.misc.ping",
    "cogs.misc.tags",
    "cogs.misc.request",
    "cogs.misc.reminder",
    "cogs.misc.info",
    "cogs.misc.stats",
    # "cogs.misc.imgur",
    # Config commands
    "cogs.config.config",
    "cogs.config.modmail",
    "cogs.config.setup",
    "cogs.config.prefix",
    # "cogs.config.blacklist",
    # Admin commands
    "cogs.admintools.shutdown",
    "cogs.admintools.showdm",
    # Profile commands
    "cogs.profile.userstats",
    "cogs.profile.avatar",
    # Other commands
    "cogs.admin",
    "cogs.clubbot.verify",
    # "cogs.config",
    # Utilities
    "utilities.events",
    # Note: "utilities.modmail" is loaded later in the code due to Order of Operations
)


def _prefix_callable(bot, msg):
    # Always allow mentioning the bot as a prefix
    base = [f"<@!{bot.user.id}> ", f"<@{bot.user.id}> "]
    # If in a guild, add the prefixes
    if msg.guild:
        bot.log.debug(f"PrefixCall: Guild found: {msg.guild.id}")
        try:
            settings = bot.guild_settings.get(msg.guild.id)
            if not settings:
                bot.log.debug(f"PrefixCall: No settings for {msg.guild.id}")
                return base
            bot.log.debug(f"PrefixCall: {msg.guild.id} | {settings.bot_prefix}")
            if settings.bot_prefix:
                base.extend(settings.bot_prefix)
        except (KeyError, AttributeError) as error:
            bot.log.warning(
                f"PrefixCall: Key/Att error. {error.__class__.__name__}:** {error}"
            )
            pass

    return base


class Bot(commands.AutoShardedBot):
    def __init__(self, log):
        super().__init__(
            command_prefix=_prefix_callable,
            description=__description__,
            help_command=commands.DefaultHelpCommand(dm_help=True),
            case_insensitive=True,
            fetch_offline_members=True,
            max_messages=20000,
        )
        self.database = None
        self.version = __version__
        self.log = log
        self.log.info("/*********Starting App*********\\")
        self.log.info(f"App Name: {__botname__} | Version: {__version__}")
        self.started_time = datetime.utcnow()
        self.botconfig = botconfig
        self.constants = Constants()
        self.owner = None
        self.guild_settings = {}
        self.activity_index = {}
        self.cooldown_settings = None
        self.session = aiohttp.ClientSession(loop=self.loop)
        self.log.debug(f"Initialized: Session Loop")
        self.database = DatabaseManager(self.botconfig)
        self.log.debug(f"Initialized: Database Manager")
        self.helpers = Helpers(self)
        self.log.debug(f"Initialized: Helpers")
        # Load the cooldown settings prior to loading Mod Mail or AntiSpam
        self.helpers.db_get_cooldown_settings()
        self.tasks = Tasks(self)
        self.log.debug(f"Initialized: Tasks")
        self.antispam = AntiSpam(self)
        self.log.debug(f"Initialized AntiSpam Feature")
        self.prompt = prompt.Prompt(self)
        self.log.debug(f"Initialized: Prompt")
        self.assignment = RoleAssignment(self)
        self.log.debug(f"Initialized: RoleAssignment")

        # Sets up the sentry_sdk integration:
        sentry_sdk.init(
            dsn=__dsn__,
            release=__version__,
            environment=__environment__,
            integrations=[SqlalchemyIntegration(), RedisIntegration()],
            before_send=self.sentry_before_send,
            traces_sample_rate=0.25,  # Sends 25% of transactions for performance sampling
            _experiments={
                "auto_enabling_integrations": True
            },  # Automatically enable all relevant transactions
        )
        self.log.debug(f"Initialized: Sentry SDK")

        for extension in initial_extensions:
            try:
                self.load_extension(extension)
                self.log.info(f"Loaded extension {extension}")
            except Exception as err:
                self.log.exception(
                    f"Failed to load extension {extension}. {sys.exc_info()[0].__name__}: {err}"
                )
        self.log.info("Done loading all extensions")

    # Perform any actions to the event prior to it being sent.
    def sentry_before_send(self, event, hint):
        # Adding in the Bot Name and Bot ID to make identifying which bot the issue is on
        event.setdefault("tags", {})["Bot_Name"] = f"{self.user if self.user else None}"
        event.setdefault("tags", {})[
            "Bot_ID"
        ] = f"{self.user.id if self.user else None}"
        return event

    def get_guild_prefixes(self, msg, *, local_inject=_prefix_callable):
        return local_inject(self, msg)

    # little hack to allow only port requests in specified channel
    async def on_message(self, message):
        if self.user == message.author:
            return

        guild = message.guild
        if guild:
          settings = self.guild_settings.get(guild.id)
          request_channel = settings.request_channel
          if message.channel.id == request_channel:
              if (
                  message.content[1:].startswith('requestport ')
                  or message.content[1:].startswith('request ')
                  or message.content[1:].startswith('rq ')
                  or message.content[1:].startswith('rqp ')
                  or message.author == self.user
              ):
                  await self.process_commands(message)
              else:
                  await message.delete()
                  return
          else:
              await self.process_commands(message)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.NoPrivateMessage):
            await ctx.author.send("This command cannot be used in private messages.")
        elif isinstance(error, commands.DisabledCommand):
            await ctx.author.send("Sorry. This command is disabled and cannot be used.")
        elif isinstance(error, commands.CommandInvokeError):
            self.log.exception(
                f"In {ctx.command.qualified_name}: {error.original.__class__.__name__}: {error.original}"
            )
        elif isinstance(error, commands.UserInputError):
            await ctx.author.send(
                f"Sorry. There was a user error processing command: **{ctx.command.qualified_name}**.\n\n**{error.__class__.__name__}:** {error}"
            )
        elif isinstance(error, commands.BadArgument):
            await ctx.author.send(
                f"Sorry. There was a bad argument error processing command: **{ctx.command.qualified_name}**.\n\n**{error.__class__.__name__}:** {error}"
            )
        # Responds to user if _the user_ is missing permission to use the command
        elif isinstance(error, commands.MissingPermissions):
            await ctx.author.send(f"**{error.__class__.__name__}:** {error}")
        # Responds to user if _the bot_ is missing permission to use the command
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.author.send(f"**{error.__class__.__name__}:** {error}")
        # Checks if user is listed as a Bot Owner
        elif isinstance(error, commands.NotOwner):
            await ctx.author.send(
                f"**{error.__class__.__name__}:** {error} This command is only for bot owners."
            )
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.author.send(f"**{error.__class__.__name__}:** {error}.")

    async def on_ready(self):
        # Gets all guild settings:
        self.helpers.get_all_guild_settings()
        # Load the cooldowns
        await self.antispam.set_cooldown_buckets()
        # Load the reminders
        await self.helpers.load_reminders()
        # Starts all tasks
        await self.tasks.start_tasks()
        self.log.info(f"Started all Tasks")

        # Load the mod mail
        try:
            self.load_extension("utilities.modmail")
            self.log.info(f"Loaded extension utilities.modmail")
        except commands.ExtensionAlreadyLoaded:
            pass

        # Sets bot owner information
        app_info = await self.application_info()
        try:
            if app_info.team:
                self.owner = app_info.team.members
                self.owner_ids = {member.id for member in app_info.team.members}
                self.log.info(f"AppInfo found Team, so setting for team of owners.")
            else:
                self.owner = app_info.owner
                self.owner_id = app_info.owner.id
                self.log.info(f"AppInfo is missing Team, so setting for single owner.")
        except Exception as err:
            self.log.exception(
                f"Failed to set bot owner information. {sys.exc_info()[0].__name__}: {err}"
            )

        # Sets activity status
        try:
            if __environment__ == "Development":
                await self.change_presence(
                    activity=discord.Game(name=f"In Dev v{__version__}")
                )
        except Exception as err:
            self.log.exception(
                f"Failed to set presence info. {sys.exc_info()[0].__name__}: {err}"
            )

        # All ready
        self.log.info(f"Ready: {self.user} ({self.user.id})")

    async def on_resumed(self):
        self.log.debug("Resumed Discord session...")

    async def on_error(self, event_method, *args, **kwargs):
        self.log.exception(
            f"An error was caught. Event Method: {event_method}. {sys.exc_info()[0].__name__}: {sys.exc_info()[1]}"
        )

    async def close(self):
        self.log.info("Caught Keyboard Interrupt. Gracefully closing sessions.")
        # Close all bot tasks
        try:
            await self.tasks.cancel_all_tasks()
        except Exception as err:
            pass
        # Close database manager
        if self.database:
            try:
                self.database.close_engine()
            except Exception as err:
                pass
        # Close the bot
        await super().close()
        # Close the core session keeping bot alive
        await self.session.close()

    def run(self):
        super().run(__token__, reconnect=True)
