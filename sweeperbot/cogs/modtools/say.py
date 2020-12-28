import sys
import typing

import discord
from discord.ext import commands


class Say(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def say(
        self,
        ctx,
        channel: typing.Optional[discord.TextChannel] = None,
        *,
        message_content: str,
    ):
        """Send a message as the bot to the specified channel.

        Requires Permission: Manage Guild

        Parameters
        -----------
        ctx: context
            The context message involved.
        channel: Optional[discord.TextChannel]
            The channel the message should be sent to. If none specified uses current
            channel.
        message_content: str
            The message the bot should send.
        """

        try:
            self.bot.log.info(
                f"CMD {ctx.invoked_with} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            await ctx.message.delete()

            # If no channel specified uses channel command was called from.
            if not channel:
                channel = ctx.channel

            if len(message_content) == 0:
                return await ctx.message.author.send(
                    f"Please provide a message to send."
                )

            if not channel.permissions_for(ctx.me).send_messages:
                return await ctx.message.author.send(
                    f"Missing permissions to send in {channel.mention}."
                )

            await channel.send(message_content)

        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error responding to {ctx.invoked_with} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
        except Exception as err:
            self.bot.log.exception(
                f"Error responding to {ctx.invoked_with} via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )


def setup(bot):
    bot.add_cog(Say(bot))
