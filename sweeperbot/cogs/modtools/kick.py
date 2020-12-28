import sys
from datetime import datetime

import discord
from discord.ext import commands
from sqlalchemy.exc import DBAPIError

from sweeperbot.db import models


class Kick(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["k"])
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick(self, ctx, user_id: str, *, action_text: str):
        """Adds a database record for the user, attempts to message the user about the kick, then kicks from the guild.

        Example:

        kick userID this is a test message
        kick @wumpus#0000 this is a test message
        k @wumpus#0000 this is a test message

        Requires Permission: Manage Messages

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
            # Don't allow you to kick yourself or the guild owner, or itself or other bots.
            if (
                user.id
                in [ctx.message.author.id, ctx.message.guild.owner.id, self.bot.user.id]
                or user.bot
            ):
                return await ctx.send(
                    f"Sorry, but you are not allowed to do that action to that user."
                )

            # Set some meta data
            action_type = "Kick"
            guild = ctx.message.guild
            settings = self.bot.guild_settings.get(guild.id)
            modmail_enabled = settings.modmail_server_id

            # Confirm the action
            confirm = await self.bot.prompt.send(
                ctx, f"Are you sure you want to kick {user} ({user.id})?"
            )
            if confirm is False or None:
                return await ctx.send("Aborting kicking that user.")
            elif confirm:
                # Try to message the user
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
                        message += self.bot.constants.footer_no_modmail.format(
                            guild=guild
                        )
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

                # Try and log to the database
                new_kick = None
                try:
                    # Get mod's DB profile
                    db_mod = await self.bot.helpers.db_get_user(
                        session, ctx.message.author.id
                    )
                    # Get the DB profile for the guild
                    db_guild = await self.bot.helpers.db_get_guild(session, guild.id)
                    # Get the DB profile for the user
                    db_user = await self.bot.helpers.db_get_user(session, user.id)

                    # Log the action to the database
                    # Edit the action_text to indicate success or failure on informing the user.
                    if msg_success:
                        action_text += " | **Msg Delivered: Yes**"
                    else:
                        action_text += " | **Msg Delivered: No**"
                    logged_action = models.Action(mod=db_mod, server=db_guild)
                    new_kick = models.Kick(
                        text=action_text,
                        user=db_user,
                        server=db_guild,
                        action=logged_action,
                    )
                    session.add(new_kick)
                    session.commit()
                    db_logged = True
                except Exception as err:
                    self.bot.log.exception(f"Error logging {action_type} to database.")
                    db_logged = False

                # Create the embed of info
                description = (
                    f"**Member:** {user} ({user.id})\n"
                    f"**Moderator:** {ctx.message.author} ({ctx.message.author.id})\n"
                    f"**Reason:** {action_text[:1900]}"
                )

                embed = discord.Embed(
                    color=0x0083FF,
                    timestamp=datetime.utcnow(),
                    title=f"A user was kicked | *#{new_kick.id}*",
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

                # Now that we've handled messaging the user, let's kick them
                try:
                    if isinstance(user, discord.member.Member):
                        reason_text = f"Mod: {ctx.message.author} ({ctx.message.author.id}) | Reason: {action_text[:400]}"
                        await guild.kick(user, reason=reason_text)
                        if db_logged:
                            response = f"A {action_type} was successfully logged and actioned for: {user} ({user.id}).\n\n{user_informed}"
                        else:
                            response = f"A {action_type} was unable to be logged, however it was successfully actioned for: {user} ({user.id}).\n\n{user_informed}"
                        await ctx.send(response)
                    else:
                        raise Exception(
                            "User is not in the guild, unable to kick them."
                        )
                except Exception as err:
                    self.bot.log.warning(
                        f"Failed to kick user. Error: {sys.exc_info()[0].__name__}: {err}"
                    )
                    await ctx.send(
                        f"Successfully logged a {action_type} for: {user} ({user.id}), however **unable to kick them.** This could mean they weren't in the server.\n\n{user_informed}"
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
                f"Error with database calls in CMD {ctx.command} for: ({user_id}). {sys.exc_info()[0].__name__}: {err}"
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
    bot.add_cog(Kick(bot))
