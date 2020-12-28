import sys

import discord
from discord.ext import commands
from sqlalchemy.exc import DBAPIError, IntegrityError

from sweeperbot.cogs.utils.paginator import Pages
from sweeperbot.db import models
from sweeperbot.utilities.helpers import set_sentry_scope


class Blacklist(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @commands.group(invoke_without_command=True)
    async def blacklist(self, ctx, user_id: int):
        """Checks if a user is blacklisted.

        Requires Permission: Manage Messages

        Example:
        -------
        blacklist userid
        blacklist 123456789123456789

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_id: int
            The user/member the action is related to. Can be an ID or a mention
        """

        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            # Get the user from user_id
            user = await self.bot.helpers.get_member_or_user(user_id, ctx.message.guild)
            if not user:
                return await ctx.send(
                    f"Unable to find the requested user: {user_id}. Please make sure the user ID is valid."
                )

            # Check if user is blacklisted, if so, ignore.
            if await self.bot.helpers.check_if_blacklisted(
                user.id, ctx.message.guild.id
            ):
                self.bot.log.debug(f"User {user} ({user.id}) is Blacklisted")
                return await ctx.send(
                    f"\N{CROSS MARK} That user is currently blacklisted: {user} ({user.id})"
                )
            else:
                self.bot.log.debug(f"User {user} ({user.id}) is NOT Blacklisted")
                return await ctx.send(
                    f"\N{WHITE HEAVY CHECK MARK} That user is **NOT** blacklisted: {user} ({user.id})"
                )
        except discord.HTTPException as err:
            set_sentry_scope(ctx)
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except Exception as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Error responding to {ctx.command} via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )

    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @blacklist.command(aliases=["a", "A"])
    async def add(self, ctx, user_id: int):
        """Adds a user to the blacklist.

        Requires Permission: Manage Messages

        Example:
        -------
        blacklist add userid
        blacklist add 123456789123456789

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_id: int
            The user/member the action is related to. Can be an ID.
        """
        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            # Get the user from user_id
            user = await self.bot.helpers.get_member_or_user(user_id, ctx.message.guild)
            if not user:
                return await ctx.send(
                    f"Unable to find the requested user: {user_id}. Please make sure the user ID is valid."
                )

            # Get the DB ID for the user
            db_user = await self.bot.helpers.db_get_user(session, user_id)
            # Get the DB ID for the guild
            db_guild = await self.bot.helpers.db_get_guild(
                session, ctx.message.guild.id
            )
            # Add to blacklist
            record = models.Blacklist(user=db_user, server=db_guild, blacklisted=True)
            session.add(record)
            session.commit()
            self.bot.log.debug(f"Blacklist: User {user} ({user.id}) added to blacklist")
            return await ctx.send(
                f"\N{WHITE HEAVY CHECK MARK} That user {user} ({user.id}) is now Blacklisted"
            )

        except discord.HTTPException as err:
            set_sentry_scope(ctx)
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except IntegrityError as err:
            self.bot.log.debug(f"Duplicate database record for {user_id}")
            await ctx.send(f"That user is already on the blacklist.")
            session.rollback()
        except DBAPIError as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Error processing database query. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
            session.rollback()
        except Exception as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Error responding to {ctx.command} via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        finally:
            session.close()

    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @blacklist.command(aliases=["d", "D", "r", "R", "remove"])
    async def delete(self, ctx, user_id: int):
        """Removes a user from the blacklist.

        Requires Permission: Manage Messages

        Example:
        -------
        blacklist remove userid
        blacklist remove 123456789123456789

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_id: int
            The user/member the action is related to. Can be an ID.
        """
        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            # Get the user from user_id
            user = await self.bot.helpers.get_member_or_user(user_id, ctx.message.guild)
            if not user:
                return await ctx.send(
                    f"Unable to find the requested user: {user_id}. Please make sure the user ID is valid."
                )

            confirm = await self.bot.prompt.send(
                ctx,
                f"Are you sure you want to remove {user} ({user.id}) from the blacklist?",
            )
            if confirm:
                # Get the DB ID for the user
                db_user = await self.bot.helpers.db_get_user(session, user_id)
                # Get the DB ID for the guild
                db_guild = await self.bot.helpers.db_get_guild(
                    session, ctx.message.guild.id
                )
                # Get blacklist record
                user_status = (
                    session.query(models.Blacklist)
                    .filter(models.Blacklist.server_id == db_guild.id)
                    .filter(models.Blacklist.user_id == db_user.id)
                    .first()
                )
                if not user_status:
                    return await ctx.send(
                        f"That user is not on blacklist, unable to remove."
                    )
                session.delete(user_status)
                session.commit()
                self.bot.log.debug(
                    f"Blacklist: User {user} ({user.id}) removed from blacklist"
                )
                await ctx.send(
                    f"\N{WHITE HEAVY CHECK MARK} Successfully removed following user from the blacklist: {user} ({user.id})"
                )
            elif confirm is False:
                return await ctx.send("\N{CROSS MARK} Cancelling request.")
            elif confirm is None:
                return await ctx.send("\N{CROSS MARK} Request timed out.")

        except discord.HTTPException as err:
            set_sentry_scope(ctx)
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except DBAPIError as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Error processing database query. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
            session.rollback()
        except Exception as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Error responding to {ctx.command} via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        finally:
            session.close()

    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @blacklist.command(aliases=["v", "V"])
    async def view(self, ctx):
        """Views the entire blacklist.

        Requires Permission: Manage Messages

        Example:
        -------
        blacklist view
        """
        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # Get the DB ID for the guild
            db_guild = await self.bot.helpers.db_get_guild(
                session, ctx.message.guild.id
            )
            # Get blacklist record
            guild_blacklist = (
                session.query(models.Blacklist)
                .filter(models.Blacklist.server_id == db_guild.id)
                .filter(models.Blacklist.blacklisted == True)
                .all()
            )

            if not guild_blacklist:
                return await ctx.send(f"This guild has no-one on the blacklist.")

            p = Pages(
                ctx,
                per_page=20,
                entries=tuple(
                    f"**User ID:** {row.user.discord_id} | **Added:** {row.created.replace(microsecond=0)}"
                    for row in guild_blacklist
                ),
            )
            p.embed.set_author(
                name=f"All Blacklisted Users for: {ctx.message.guild} ({ctx.message.guild.id})",
                icon_url=ctx.message.guild.icon_url,
            )
            await p.paginate()

        except discord.HTTPException as err:
            set_sentry_scope(ctx)
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except DBAPIError as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Error processing database query. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
            session.rollback()
        except Exception as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Error responding to {ctx.command} via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        finally:
            session.close()


def setup(bot):
    bot.add_cog(Blacklist(bot))
