import sys

import discord
from discord.ext import commands
from sqlalchemy import exc


class Config(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.group(
        name="Config.ModMail",
        aliases=["mmconfig", "mmconfigure"],
        case_insensitive=True,
        invoke_without_command=False,
    )
    async def mmconfig(self, ctx):
        """Allows for setting various mod mail configuration."""
        pass

    @commands.guild_only()
    @commands.is_owner()
    @mmconfig.command(aliases=["serverid"])
    async def server(self, ctx, modmail_server_id: int):
        """Sets the mod mail server ID.

        Example:

        mmconfig server serverID
        mmconfig server 123456

        Requires Permission: Bot Owner

        Parameters
        -----------
        ctx: context
            The context message involved.
        modmail_server_id: int
            Server ID of the Mod Mail server.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            mm_guild = self.bot.get_guild(modmail_server_id)

            # Get the guild settings and update the setting
            settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            settings.modmail_server_id = mm_guild.id
            session.commit()

            # Update local cache
            self.bot.guild_settings[
                ctx.message.guild.id
            ] = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            return await ctx.send(
                f"Successfully set the mod mail server to: {mm_guild.name} ({mm_guild.id})."
            )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error setting modmail server id. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
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
    @mmconfig.command()
    async def unanswered(self, ctx, category_id: int):
        """Sets the mod mail unanswered category ID.

        Example:

        mmconfig unanswered categoryID
        mmconfig unanswered 123456

        Requires Permission: Manage Guild

        Parameters
        -----------
        ctx: context
            The context message involved.
        category_id: int
            Category ID for the Unanswered category in the Mod Mail server.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            mm_category = self.bot.get_channel(category_id)

            # Get the guild settings and update the setting
            settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            settings.modmail_unanswered_cat_id = mm_category.id
            session.commit()

            # Update local cache
            self.bot.guild_settings[
                ctx.message.guild.id
            ] = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            return await ctx.send(
                f"Successfully set the mod mail unanswered category to: {mm_category.name} ({mm_category.id})."
            )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error setting unanswered category id. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
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
    @mmconfig.command()
    async def inprogress(self, ctx, category_id: int):
        """Sets the mod mail inprogress category ID.

        Example:

        mmconfig inprogress categoryID
        mmconfig inprogress 123456

        Requires Permission: Manage Guild

        Parameters
        -----------
        ctx: context
            The context message involved.
        category_id: int
            Category ID for the In Progress category in the Mod Mail server.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            mm_category = self.bot.get_channel(category_id)

            # Get the guild settings and update the setting
            settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            settings.modmail_in_progress_cat_id = mm_category.id
            session.commit()

            # Update local cache
            self.bot.guild_settings[
                ctx.message.guild.id
            ] = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            return await ctx.send(
                f"Successfully set the mod mail In Progress category to: {mm_category.name} ({mm_category.id})."
            )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error setting In Progress category id. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
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


def setup(bot):
    bot.add_cog(Config(bot))
