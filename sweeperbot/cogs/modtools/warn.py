import sys
import typing
from datetime import datetime

import discord
from discord.ext import commands
from sqlalchemy.exc import DBAPIError

from sweeperbot.db import models


class Warn(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["w", "warning"])
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def warn(self, ctx, user_id: str, *, action_text: str):
        """Adds a warning to a users record and attempts to message the user about the warning.

        Example:

        warn userID this is a test warning
        w @wumpus#0000 this is a test warning

        Requires Permission: Manage Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_id: str
            The user/member the warning is related to. Can be an ID or a mention
        action_text: str
            The action text you are adding to the record.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            user = await self.bot.helpers.get_member_or_user(user_id, ctx.message.guild)
            if not user:
                return await ctx.send(
                    f"Unable to find the requested user. Please make sure the user ID or @ mention is valid."
                )
            # Don't allow you to action yourself or itself, or other bots.
            if user.id in [ctx.message.author.id, self.bot.user.id] or user.bot:
                return await ctx.send(
                    f"Sorry, but you are not allowed to do that action to that user."
                )
            # Set some meta data
            action_type = "warning"
            guild = ctx.message.guild
            settings = self.bot.guild_settings.get(guild.id)
            modmail_enabled = settings.modmail_server_id

            # Attempts to warn the user:
            try:
                # Format the message
                message = self.bot.constants.infraction_header.format(
                    action_type=action_type, guild=guild
                )

                # Reduces the text to 1,800 characters to leave enough buffer for header and footer text
                message += f"'{action_text[:1800]}'"
                # Set footer based on if the server has modmail or not
                if modmail_enabled:
                    message += self.bot.constants.footer_with_modmail.format(
                        guild=guild
                    )
                else:
                    message += self.bot.constants.footer_no_modmail.format(guild=guild)
                await user.send(message)
                user_informed = (
                    f"User was successfully informed of their {action_type}."
                )
                msg_success = True
            except discord.errors.Forbidden as err:
                self.bot.log.warning(
                    f"Error sending {action_type} to user. Bot is either blocked by user or doesn't share a server. Error: {sys.exc_info()[0].__name__}: {err}"
                )
                user_informed = f"User was unable to be informed of their {action_type}. They might not share a server with the bot, their DM's might not allow messages, or they blocked the bot."
                msg_success = False

            # Get mod's DB profile
            db_mod = await self.bot.helpers.db_get_user(session, ctx.message.author.id)
            # Get the DB profile for the guild
            db_guild = await self.bot.helpers.db_get_guild(session, guild.id)
            # Get the DB profile for the user
            db_user = await self.bot.helpers.db_get_user(session, user.id)
            # Logs warning to database
            logged_action = models.Action(mod=db_mod, server=db_guild)
            # Edit the action_text to indicate success or failure on informing the user.
            if msg_success:
                action_text += " | **Msg Delivered: Yes**"
            else:
                action_text += " | **Msg Delivered: No**"
            new_warn = models.Warn(
                text=action_text, user=db_user, server=db_guild, action=logged_action
            )
            session.add(new_warn)
            session.commit()

            # Create the embed of info
            description = (
                f"**Member:** {user} ({user.id})\n"
                f"**Moderator:** {ctx.message.author} ({ctx.message.author.id})\n"
                f"**Reason:** {action_text[:1900]}"
            )

            embed = discord.Embed(
                color=0xFFEF00,
                timestamp=datetime.utcnow(),
                title=f"A user was warned | *#{new_warn.id}*",
                description=description,
            )
            embed.set_author(name=f"{user} ({user.id})", icon_url=user.avatar_url)
            # Try and get the logs channel
            logs = discord.utils.get(guild.text_channels, name="bot-logs")

            if not logs:
                # If there is no normal logs channel, try the sweeper (legacy) logs channel
                logs = discord.utils.get(guild.text_channels, name="sweeper-logs")

            if logs:
                # Checks if the bot can even send messages in that channel
                if (
                    logs.permissions_for(logs.guild.me).send_messages
                    and logs.permissions_for(logs.guild.me).embed_links
                ):
                    await logs.send(embed=embed)

            await ctx.send(
                f"Successfully logged {action_type} for: {user} ({user.id}).\n\n{user_informed}"
            )
        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except DBAPIError as err:
            self.bot.log.exception(
                f"Error logging action to database. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. **Action is not likely logged to the database and user is most likely NOT informed. Do a history check to validate.** Error has already been reported to my developers."
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

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def warnun(
        self,
        ctx,
        user_id: str,
        *,
        action_text: typing.Optional[
            str
        ] = "Hello there. We have adjusted your nickname as your current nickname/username is in violation of our rules. You are welcome to update it so long as it is in compliance. Thank you for your understanding.",
    ):
        """Adds a warning (about their username/nickname) to a users record and attempts to message the user about the warning.

        Example:

        warnun userID
        warnun @wumpus#0000

        Requires Permission: Manage Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_id: str
            The user/member the warning is related to. Can be an ID or a mention
        action_text: typing.Optional[str]
            The action text you are adding to the record. You can specify your own, or leave blank and by default it is: "Hello there. We have adjusted your nickname as your current nickname/username is in violation of our rules. You are welcome to update it so long as it is in compliance. Thank you for your understanding."
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            user = await self.bot.helpers.get_member_or_user(user_id, ctx.message.guild)
            if not user:
                return await ctx.send(
                    f"Unable to find the requested user. Please make sure the user ID or @ mention is valid."
                )
            # Don't allow you to action yourself or itself, or other bots.
            if user.id in [ctx.message.author.id, self.bot.user.id] or user.bot:
                return await ctx.send(
                    f"Sorry, but you are not allowed to do that action to that user."
                )
            # Set some meta data
            action_type = "warning"
            guild = ctx.message.guild
            settings = self.bot.guild_settings.get(guild.id)
            modmail_enabled = settings.modmail_server_id

            # Attempts to warn the user:
            try:
                # Format the message
                message = self.bot.constants.infraction_header.format(
                    action_type=action_type, guild=guild
                )

                # Reduces the text to 1,800 characters to leave enough buffer for header and footer text
                message += f"'{action_text[:1800]}'"
                # Set footer based on if the server has modmail or not
                if modmail_enabled:
                    message += self.bot.constants.footer_with_modmail.format(
                        guild=guild
                    )
                else:
                    message += self.bot.constants.footer_no_modmail.format(guild=guild)
                await user.send(message)
                user_informed = (
                    f"User was successfully informed of their {action_type}."
                )
                msg_success = True
            except discord.errors.Forbidden as err:
                self.bot.log.warning(
                    f"Error sending {action_type} to user. Bot is either blocked by user or doesn't share a server. Error: {sys.exc_info()[0].__name__}: {err}"
                )
                user_informed = f"User was unable to be informed of their {action_type}. They might not share a server with the bot, their DM's might not allow messages, or they blocked the bot."
                msg_success = False

            # Get mod's DB profile
            db_mod = await self.bot.helpers.db_get_user(session, ctx.message.author.id)
            # Get the DB profile for the guild
            db_guild = await self.bot.helpers.db_get_guild(session, guild.id)
            # Get the DB profile for the user
            db_user = await self.bot.helpers.db_get_user(session, user.id)
            # Logs warning to database
            logged_action = models.Action(mod=db_mod, server=db_guild)
            # Edit the action_text to indicate success or failure on informing the user.
            if msg_success:
                action_text += " | **Msg Delivered: Yes**"
            else:
                action_text += " | **Msg Delivered: No**"
            new_warn = models.Warn(
                text=action_text, user=db_user, server=db_guild, action=logged_action
            )
            session.add(new_warn)
            session.commit()

            # Create the embed of info
            description = (
                f"**Member:** {user} ({user.id})\n"
                f"**Moderator:** {ctx.message.author} ({ctx.message.author.id})\n"
                f"**Reason:** {action_text[:1900]}"
            )

            embed = discord.Embed(
                color=0xFFEF00,
                timestamp=datetime.utcnow(),
                title=f"A user was warned | *#{new_warn.id}*",
                description=description,
            )
            embed.set_author(name=f"{user} ({user.id})", icon_url=user.avatar_url)
            # Try and get the logs channel
            logs = discord.utils.get(guild.text_channels, name="bot-logs")

            if not logs:
                # If there is no normal logs channel, try the sweeper (legacy) logs channel
                logs = discord.utils.get(guild.text_channels, name="sweeper-logs")

            if logs:
                # Checks if the bot can even send messages in that channel
                if (
                    logs.permissions_for(logs.guild.me).send_messages
                    and logs.permissions_for(logs.guild.me).embed_links
                ):
                    await logs.send(embed=embed)

            await ctx.send(
                f"Successfully logged {action_type} for: {user} ({user.id}).\n\n{user_informed}"
            )
        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except DBAPIError as err:
            self.bot.log.exception(
                f"Error logging action to database. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. **Action is not likely logged to the database and user is most likely NOT informed. Do a history check to validate.** Error has already been reported to my developers."
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
    bot.add_cog(Warn(bot))
