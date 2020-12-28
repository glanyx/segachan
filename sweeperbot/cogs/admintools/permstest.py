import sys

import discord
from discord.ext import commands

from sweeperbot.utilities.helpers import has_guild_permissions


class PermsTest(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @has_guild_permissions(manage_messages=True, ban_members=True)
    @commands.guild_only()
    async def perms(self, ctx):
        """A proof of concept demonstrating the use of a custom decorator to check if the author has permissions on the Guild level.

        This is important as permissions can be either on the Guild level (roles), channel level (roles), channel level (user override), or all summed together.

        The Discord.py built in @has_permissions() decorator check is on the channel level. This causes issues for mod commands as we use 'manage messages' permission for mod commands like warn, note, history, etc. A user could be given manage messages on a channel level, but not be considered a mod to the point a server would want them to have access to all mod commands, ex history. By not using this new custom decorator it leaves open an exploit where someone given perms only to manage messages in one channel could see the user history of all users in the server."""

        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            await ctx.send("You have permission")
        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except Exception as err:
            self.bot.log.exception(
                f"Error responding to {ctx.command} via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )


def setup(bot):
    bot.add_cog(PermsTest(bot))
