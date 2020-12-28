import sys

import discord
from discord.ext import commands
from sqlalchemy.exc import DBAPIError


class Prefix(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.guild_only()
    @commands.has_permissions(send_messages=True)
    @commands.group(invoke_without_command=True)
    async def prefix(self, ctx):
        """Show currently available prefixes. Mentioning the bot will always be available.

        Requires Permission: Send Messages
        """
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            # Check if user is blacklisted, if so, ignore.
            if await self.bot.helpers.check_if_blacklisted(
                ctx.message.author.id, ctx.message.guild.id
            ):
                self.bot.log.debug(
                    f"User {ctx.message.author} ({ctx.message.author.id}) Blacklisted, unable to use command {ctx.command}"
                )
                return

            # Get current prefixes
            embed = self.get_current_prefixes(ctx)
            await ctx.send(embed=embed)

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

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @prefix.command(aliases=["a", "A"])
    async def add(self, ctx, newprefix: str):
        """Adds a prefix to the available server specific list. Mentioning the bot will always be available.

        To add a multi word prefix, or add a space to the end of the prefix allowing for "prefix command" instead of "prefixcommand" use double quotes `"` to surround the new prefix.

        Requires Permission: Manage Guild"""

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # Get current prefixes stored from the database
            guild_settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            # If the prefix list is null/broken, start fresh
            if guild_settings.bot_prefix is None:
                guild_settings.bot_prefix = []

            current_prefixes = []
            for prefix in guild_settings.bot_prefix:
                current_prefixes.append(prefix)

            if newprefix not in current_prefixes:
                current_prefixes.append(newprefix)
                # Save to database
                guild_settings.bot_prefix = current_prefixes
                session.commit()
                # Update local cache
                self.bot.guild_settings[
                    ctx.message.guild.id
                ] = await self.bot.helpers.get_one_guild_settings(
                    session, ctx.message.guild.id
                )

                # Get current prefixes
                embed = self.get_current_prefixes(ctx)
                await ctx.send(embed=embed)
            else:
                await ctx.send(
                    f"That prefix already exists. Use `<@!{self.bot.user.id}> prefix` command to see current prefixes available."
                )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except DBAPIError as err:
            self.bot.log.exception(
                f"Error getting adding guild prefix for {ctx.message.guild.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            session.rollback()
        except Exception as err:
            self.bot.log.exception(
                f"Error responding to {ctx.command} via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        finally:
            session.close()

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @prefix.command(aliases=["r", "R", "d", "D", "delete"])
    async def remove(self, ctx, oldprefix: str):
        """Removes a prefix from the available server specific list. Mentioning the bot will always be available.

        To remove a multi word prefix use double quotes `"` to surround the prefix.

        Requires Permission: Manage Guild"""

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # Get current prefixes stored from the database
            guild_settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            # If there are no prefixes, don't continue
            if guild_settings.bot_prefix is None:
                return await ctx.send(
                    f"You do not have any custom prefixes. Try '<@!{self.bot.user.id}> prefix add' command to add one."
                )

            current_prefixes = []
            for prefix in guild_settings.bot_prefix:
                current_prefixes.append(prefix)

            # Make sure prefix is in the list before modifications
            if oldprefix in current_prefixes:
                current_prefixes.remove(oldprefix)
                # Save to the database
                guild_settings.bot_prefix = current_prefixes
                session.commit()
                # Update local cache
                self.bot.guild_settings[
                    ctx.message.guild.id
                ] = await self.bot.helpers.get_one_guild_settings(
                    session, ctx.message.guild.id
                )

                # Get current prefixes
                embed = self.get_current_prefixes(ctx)
                await ctx.send(embed=embed)
            else:
                await ctx.send(
                    f"The prefix `{oldprefix}` was not found in the list. Use `<@!{self.bot.user.id}> prefix` command to see current prefixes available."
                )
        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except DBAPIError as err:
            self.bot.log.exception(
                f"Error getting removing guild prefix for {ctx.message.guild.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            session.rollback()
        except Exception as err:
            self.bot.log.exception(
                f"Error responding to {ctx.command} via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        finally:
            session.close()

    def get_current_prefixes(self, ctx):
        # Get current prefix
        prefixes = self.bot.get_guild_prefixes(ctx.message)
        # Remove the duplicate @bot#discrim mention to avoid confusion
        prefixes.pop(1)
        # Create embed of all prefixes
        embed = discord.Embed(title="Current Prefixes", colour=discord.Colour.blurple())
        embed.set_footer(text=f"{len(prefixes)} prefixes")
        prefix_desc = []
        index = 0
        for prefix in prefixes:
            index += 1
            temp = f"{index}: `{prefix}`"
            prefix_desc.append(temp)
        embed.description = "\n".join(prefix_desc)
        return embed


def setup(bot):
    bot.add_cog(Prefix(bot))
