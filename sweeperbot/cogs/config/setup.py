import sys
import typing

import discord
from discord.ext import commands


class Setup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def setup(self, ctx, type: str, parameter: typing.Optional[str] = None):
        """Setup command for creating features on the server.

        Currently supports creating the bot logs channels. Usage:

        setup logs all"""
        try:
            self.bot.log.info(
                f"CMD {ctx.invoked_with} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            await ctx.message.delete()

            # If no type specified, abort.
            if not type:
                return await ctx.message.author.send(
                    f"Please provide a type to setup. For help see `<@{self.bot.user.id}> help {ctx.invoked_with}`."
                )

            # Type options
            channels_processed = []
            if type.lower() == "logs":
                # If no parameter type set
                if not parameter or parameter not in ["all"]:
                    return await ctx.message.author.send(
                        f"Please provide a parameter for logs setup. For help see '<@{self.bot.user.id}> help {ctx.invoked_with}'."
                    )
                # Check if there is a Bot Logs category
                category = await discord.utils.find(
                    lambda cat: cat.name == "bot logs", ctx.message.guild.categories
                )
                if not category:
                    # Create the permission overwrites
                    overwrites = {
                        ctx.me: discord.PermissionOverwrite(
                            read_messages=True, send_messages=True, embed_links=True
                        ),
                        ctx.message.guild.default_role: discord.PermissionOverwrite(
                            read_messages=False, send_messages=False
                        ),
                    }
                    # Creates the category
                    category = await ctx.message.guild.create_category(
                        "Bot Logs", overwrites=overwrites
                    )
                    self.bot.log.info(
                        f"CMD {ctx.invoked_with} | Created category {category.name} ({category.id}) in guild {ctx.message.guild.id}"
                    )
                # Create all the channels
                if parameter.lower() == "all":
                    for channel_name in self.bot.constants.log_channels:
                        # Tries to find the channel. If it doesn't exist will create it under the category
                        channel = discord.utils.find(
                            lambda chan: chan.name == channel_name,
                            ctx.message.guild.text_channels,
                        )
                        if not channel:
                            channel = await ctx.message.guild.create_text_channel(
                                category=category, name=channel_name
                            )
                            self.bot.log.info(
                                f"CMD {ctx.invoked_with} | Created channel {channel.name} ({channel.id}) in guild {ctx.message.guild.id}"
                            )
                        channels_processed.append(channel)

                    # Done creating any channels needed
                    await ctx.send(
                        f"Done setting up. Category: {category.mention}. Channels: {[channel.mention for channel in channels_processed]}. Please be sure to have an Admin or the Owner make any permission adjustments necessary."
                    )

        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error responding to {ctx.invoked_with} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
        except Exception as err:
            self.bot.log.exception(
                f"Error responding to {ctx.invoked_with} via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )


def setup(bot):
    bot.add_cog(Setup(bot))
