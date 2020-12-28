import sys
import typing
from datetime import datetime

import discord
from discord.ext import commands
from sqlalchemy.exc import DBAPIError

from sweeperbot.cogs.utils.paginator import FieldPages
from sweeperbot.utilities.helpers import has_guild_permissions


class Ban(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["b"])
    @commands.guild_only()
    @has_guild_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(
        self, ctx, user_id: str, days: typing.Optional[int] = 0, *, action_text: str
    ):
        """Adds a database record for the user, attempts to message the user about the ban, then bans from the guild.

        You can supply an optional number of days of messages to delete, up to 7 days. Default being 0.

        Example:

        ban userID 1 this is a test message
        ban @wumpus#0000 this is a test message
        b @wumpus#0000 7 this is a test message

        Requires Permission: Ban Members

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_id: str
            The user/member the action is related to. Can be an ID or a mention
        days: typing.Optional[int]
            The number of days of prior messages to delete from the user. Default 0.
        action_text: str
            The action text you are adding to the record.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            # Get the user profile
            user = await self.bot.helpers.get_member_or_user(user_id, ctx.message.guild)
            if not user:
                return await ctx.send(
                    f"Unable to find the requested user. Please make sure the user ID or @ mention is valid."
                )
            # Don't allow you to action yourself or the guild owner, or itself, or other bots.
            if user.id in [
                ctx.message.author.id,
                ctx.message.guild.owner.id,
                self.bot.user.id,
            ]:
                return await ctx.send(
                    f"Sorry, but you are not allowed to do that action to that user."
                )

            # Cancel if the user is already banned
            found_ban = False
            all_bans = await ctx.message.guild.bans()
            for ban_entry in all_bans:
                if user.id == ban_entry.user.id:
                    found_ban = True
                    break

            if found_ban:
                return await ctx.send(
                    f"Unable to proceed, **{user}** ({user.id}) is already banned."
                )

            # Set some meta data
            action_type = "Ban"
            guild = ctx.message.guild
            settings = self.bot.guild_settings.get(guild.id)
            modmail_enabled = settings.modmail_server_id
            appeals_invite = settings.appeals_invite_code
            db_logged = False
            if days > 7:
                days = 7

            # Send the users history so mod team can make best decision
            (
                embed_result_entries,
                footer_text,
            ) = await self.bot.helpers.get_action_history(session, user, guild)

            p = FieldPages(ctx, per_page=8, entries=embed_result_entries)
            p.embed.color = 0xE50000
            p.embed.set_author(
                name=f"Member: {user} ({user.id})", icon_url=user.avatar_url,
            )
            p.embed.set_footer(text=footer_text)
            await p.paginate()
            # Confirm the action
            confirm = await self.bot.prompt.send(
                ctx, f"Are you sure you want to ban {user} ({user.id})?"
            )
            if confirm is False or None:
                return await ctx.send("Aborting action on that user.")
            elif confirm:
                # Try to message the user
                try:
                    # Format the message
                    message = self.bot.constants.infraction_header.format(
                        action_type=action_type.lower(), guild=guild
                    )

                    # Reduces the text to 1,800 characters to leave enough buffer for header and footer text
                    message += f"'{action_text[:1800]}'"
                    # Set footer based on if the server has modmail or not
                    if modmail_enabled:
                        message += self.bot.constants.footer_with_modmail.format(
                            guild=guild
                        )
                    else:
                        message += self.bot.constants.footer_no_modmail.format(
                            guild=guild
                        )
                    if appeals_invite:
                        message += self.bot.constants.footer_appeals_server.format(
                            appeals_invite=appeals_invite
                        )
                    await user.send(message)
                    user_informed = f"User was successfully informed of their {action_type.lower()}."
                    msg_success = True
                except discord.errors.Forbidden as err:
                    self.bot.log.warning(
                        f"Error sending {action_type.lower()} to user. Bot is either blocked by user or doesn't share a server. Error: {sys.exc_info()[0].__name__}: {err}"
                    )
                    user_informed = f"User was unable to be informed of their {action_type.lower()}. They might not share a server with the bot, their DM's might not allow messages, or they blocked the bot."
                    msg_success = False

                # Try and log to the database and logs channel
                try:
                    # Log the action to the database and logs channel
                    # Edit the action_text to indicate success or failure on informing the user.
                    if msg_success:
                        action_text += " | **Msg Delivered: Yes**"
                    else:
                        action_text += " | **Msg Delivered: No**"
                    db_logged, chan_logged = await self.bot.helpers.process_ban(
                        session,
                        user,
                        ctx.message.author,
                        guild,
                        datetime.utcnow(),
                        action_text,
                    )

                except Exception as err:
                    self.bot.log.exception(f"Error logging {action_type} to database.")

                # Now that we've handled messaging the user, let's handle the action
                try:
                    reason_text = f"Mod: {ctx.message.author} ({ctx.message.author.id}) | Reason: {action_text[:400]}"
                    await guild.ban(user, reason=reason_text, delete_message_days=days)
                    if db_logged:
                        response = f"A {action_type.lower()} was successfully logged and actioned for: {user} ({user.id}).\n\n{user_informed}"
                    else:
                        response = f"A {action_type.lower()} was unable to be logged, however it was successfully actioned for: {user} ({user.id}).\n\n{user_informed}"
                    await ctx.send(response)
                except Exception as err:
                    self.bot.log.warning(
                        f"Failed to {action_type.lower()} user. Error: {sys.exc_info()[0].__name__}: {err}"
                    )
                    await ctx.send(
                        f"Successfully logged a {action_type.lower()} for: {user} ({user.id}), however **unable to {action_type.lower()} them.**\n\n{user_informed}"
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
                f"Error processing database query for: ({user_id}). {sys.exc_info()[0].__name__}: {err}"
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

    @commands.command(aliases=["ub"])
    @commands.guild_only()
    @has_guild_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: str, *, action_text: str):
        """Adds a database record for the user, attempts to message the user about the removal of ban, then unbans from the guild.

        Example:

        unban userID this is a test message
        unban @wumpus#0000 this is a test message
        ub @wumpus#0000 this is a test message

        Requires Permission: Ban Members

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_id: str
            The user/member the action is related to. Can be an ID or a mention
        action_text: str
            The action text you are adding to the record.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            # Get the user profile
            user = await self.bot.helpers.get_member_or_user(user_id, ctx.message.guild)
            if not user:
                return await ctx.send(
                    f"Unable to find the requested user. Please make sure the user ID or @ mention is valid."
                )
            # Don't allow you to action yourself or the guild owner, or itself.
            if user.id in [
                ctx.message.author.id,
                ctx.message.guild.owner.id,
                self.bot.user.id,
            ]:
                return await ctx.send(
                    f"Sorry, but you are not allowed to do that action to that user."
                )

            # Cancel if the user is not banned
            found_ban = False
            all_bans = await ctx.message.guild.bans()
            for ban_entry in all_bans:
                if user.id == ban_entry.user.id:
                    found_ban = True
                    break

            if not found_ban:
                return await ctx.send(
                    f"Unable to proceed, **{user}** ({user.id}) is not banned."
                )

            # Set some meta data
            action_type = "Unban"
            guild = ctx.message.guild
            settings = self.bot.guild_settings.get(guild.id)
            modmail_enabled = settings.modmail_server_id

            # Send the users history so mod team can make best decision
            (
                embed_result_entries,
                footer_text,
            ) = await self.bot.helpers.get_action_history(session, user, guild)

            p = FieldPages(ctx, per_page=8, entries=embed_result_entries)
            p.embed.color = 0xBDBDBD
            p.embed.set_author(
                name=f"Member: {user} ({user.id})", icon_url=user.avatar_url,
            )
            p.embed.set_footer(text=footer_text)
            await p.paginate()

            # Confirm the action
            confirm = await self.bot.prompt.send(
                ctx, f"Are you sure you want to unban {user} ({user.id})?"
            )
            if confirm is False or None:
                return await ctx.send("Aborting action on that user.")
            elif confirm:
                # Try to message the user
                try:
                    # Format the message
                    message = self.bot.constants.infraction_header.format(
                        action_type=action_type.lower(), guild=guild
                    )

                    # Reduces the text to 1,800 characters to leave enough buffer for header and footer text
                    message += f"'{action_text[:1800]}'"
                    # Set footer based on if the server has modmail or not
                    if modmail_enabled:
                        message += self.bot.constants.footer_with_modmail.format(
                            guild=guild
                        )
                    else:
                        message += self.bot.constants.footer_no_modmail.format(
                            guild=guild
                        )
                    await user.send(message)
                    user_informed = f"User was successfully informed of their {action_type.lower()}."
                    msg_success = True
                except discord.errors.Forbidden as err:
                    self.bot.log.warning(
                        f"Error sending {action_type.lower()} to user. Bot is either blocked by user or doesn't share a server. Error: {sys.exc_info()[0].__name__}: {err}"
                    )
                    user_informed = f"User was unable to be informed of their {action_type.lower()}. They might not share a server with the bot, their DM's might not allow messages, or they blocked the bot."
                    msg_success = False

                # Try and log to the database as a note
                # Edit the action_text to indicate success or failure on informing the user.
                if msg_success:
                    action_text += " | **Msg Delivered: Yes**"
                else:
                    action_text += " | **Msg Delivered: No**"
                db_logged, chan_logged = await self.bot.helpers.process_unban(
                    session,
                    user,
                    ctx.message.author,
                    guild,
                    datetime.utcnow(),
                    action_text,
                )

                # Now that we've handled messaging the user, let's handle the action
                try:
                    reason_text = f"Mod: {ctx.message.author} ({ctx.message.author.id}) | Reason: {action_text[:400]}"
                    await guild.unban(user, reason=reason_text)
                    if db_logged:
                        response = f"An {action_type.lower()} was successfully logged and actioned for: {user} ({user.id}).\n\n{user_informed}"
                    else:
                        response = f"An {action_type.lower()} was unable to be logged, however it was successfully actioned for: {user} ({user.id}).\n\n{user_informed}"
                    await ctx.send(response)
                except Exception as err:
                    self.bot.log.warning(
                        f"Failed to {action_type.lower()} user. Error: {sys.exc_info()[0].__name__}: {err}"
                    )
                    await ctx.send(
                        f"Successfully logged an {action_type.lower()} for: {user} ({user.id}), however **unable to {action_type.lower()} them.**\n\n{user_informed}"
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
                f"Error processing database query for: ({user_id}). {sys.exc_info()[0].__name__}: {err}"
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

    @commands.command(aliases=["mb", "mban"])
    @commands.guild_only()
    @has_guild_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def massban(self, ctx, user_ids: str, *, action_text: str):
        """Performs the following actions for multiple users. This is 'Mass Ban' intended for cleaning up raids. There is no confirmation prior to the ban executing.

        Adds a database record for the user, attempts to message the user about the ban, then bans from the guild.

        A default of 1 days of messages will be deleted.

        User IDs are separated by a comma only.

        Example:

        mban userID,userID2,userID3,userID4,userID5 raiding the server
        massban userID,userID2,userID3 this is a test message

        Requires Permission: Ban Members

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_ids: str
            List of user IDs to ban, separated by a comma only
        action_text: str
            The action text you are adding to the record.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            # Set some meta data
            action_type = "Ban"
            guild = ctx.message.guild
            settings = self.bot.guild_settings.get(guild.id)
            modmail_enabled = settings.modmail_server_id
            appeals_invite = settings.appeals_invite_code

            # Split the string to a list of IDs
            all_user_ids = user_ids.split(",")
            # Get the user profile
            for user_id in all_user_ids:
                user = await self.bot.helpers.get_member_or_user(
                    user_id, ctx.message.guild
                )
                if not user:
                    await ctx.send(
                        f"Unable to find the requested user: {user_id}. Please make sure the user ID is valid."
                    )
                    continue
                # Don't allow you to action yourself or the guild owner, or itself.
                if user.id in [
                    ctx.message.author.id,
                    ctx.message.guild.owner.id,
                    self.bot.user.id,
                ]:
                    await ctx.send(
                        f"Sorry, but you are not allowed to do that action to that user: {user_id}."
                    )
                    continue

                # Cancel if the user is already banned
                found_ban = False
                all_bans = await ctx.message.guild.bans()
                for ban_entry in all_bans:
                    if user.id == ban_entry.user.id:
                        found_ban = True
                        break

                if found_ban:
                    await ctx.send(
                        f"Skipping ban on **{user}** ({user.id}), they are already banned."
                    )
                    continue

                # Set some meta info
                db_logged = False

                # Try to message the user
                try:
                    # Format the message
                    message = self.bot.constants.infraction_header.format(
                        action_type=action_type.lower(), guild=guild
                    )

                    # Reduces the text to 1,800 characters to leave enough buffer for header and footer text
                    message += f"'{action_text[:1800]}'"
                    # Set footer based on if the server has modmail or not
                    if modmail_enabled:
                        message += self.bot.constants.footer_with_modmail.format(
                            guild=guild
                        )
                    else:
                        message += self.bot.constants.footer_no_modmail.format(
                            guild=guild
                        )
                    if appeals_invite:
                        message += self.bot.constants.footer_appeals_server.format(
                            appeals_invite=appeals_invite
                        )
                    await user.send(message)
                    user_informed = f"User was successfully informed of their {action_type.lower()}."
                    msg_success = True
                except discord.errors.Forbidden as err:
                    self.bot.log.warning(
                        f"Error sending {action_type.lower()} to user. Bot is either blocked by user or doesn't share a server. Error: {sys.exc_info()[0].__name__}: {err}"
                    )
                    user_informed = f"User was unable to be informed of their {action_type.lower()}. They might not share a server with the bot, their DM's might not allow messages, or they blocked the bot."
                    msg_success = False

                # Try and log to the database and logs channel
                try:
                    # Log the action to the database and logs channel
                    # Edit the action_text to indicate success or failure on informing the user.
                    if msg_success:
                        action_text += " | **Msg Delivered: Yes**"
                    else:
                        action_text += " | **Msg Delivered: No**"
                    db_logged, chan_logged = await self.bot.helpers.process_ban(
                        session,
                        user,
                        ctx.message.author,
                        guild,
                        datetime.utcnow(),
                        action_text,
                    )

                except Exception as err:
                    self.bot.log.exception(
                        f"Error logging {action_type} to database. Error: {sys.exc_info()[0].__name__}: {err}"
                    )

                # Now that we've handled messaging the user, let's handle the action
                try:
                    reason_text = f"Mod: {ctx.message.author} ({ctx.message.author.id}) | Reason: {action_text[:400]}"
                    await guild.ban(user, reason=reason_text, delete_message_days=1)
                    if db_logged:
                        response = f"A {action_type.lower()} was successfully logged and actioned for: {user} ({user.id}).\n\n{user_informed}"
                    else:
                        response = f"A {action_type.lower()} was unable to be logged, however it was successfully actioned for: {user} ({user.id}).\n\n{user_informed}"
                    await ctx.send(response)
                except Exception as err:
                    self.bot.log.warning(
                        f"Failed to {action_type.lower()} user. Error: {sys.exc_info()[0].__name__}: {err}"
                    )
                    await ctx.send(
                        f"Successfully logged a {action_type.lower()} for: {user} ({user.id}), however **unable to {action_type.lower()} them.**\n\n{user_informed}"
                    )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Not all bans may have been processed or logged to the database. Please validate and try any remaining. Error has already been reported to my developers."
            )
        except DBAPIError as err:
            self.bot.log.exception(
                f"Error processing database query for {ctx.command}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Not all bans may have been processed or logged to the database. Please validate and try any remaining. Error has already been reported to my developers."
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
    bot.add_cog(Ban(bot))
