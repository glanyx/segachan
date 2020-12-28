import sys
from datetime import datetime

import discord
from discord.ext import commands
from sqlalchemy.exc import DBAPIError

from sweeperbot.db import models


class Request(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["portrequest", "rq", "prq"])
    @commands.has_permissions(send_messages=True)
    @commands.guild_only()
    async def request(self, ctx, *, request_body):
        """Takes input as a request and reposts it in a dedicated channel and provides voting reactions to show interest. Logs to database for record keeping.

        Requires Permission
        -------------------
        Send Messages
        """
        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.invoked_with} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            # Check if user is blacklisted, if so, ignore.
            if await self.bot.helpers.check_if_blacklisted(
                ctx.message.author.id, ctx.message.guild.id
            ):
                self.bot.log.debug(
                    f"User {ctx.message.author} ({ctx.message.author.id}) Blacklisted, unable to use command {ctx.command}"
                )
                return
            # Get channel ID's the command is allowed in
            guild = ctx.message.guild
            settings = self.bot.guild_settings.get(guild.id)
            request_channel = settings.request_channel
            request_channel_allowed = settings.request_channel_allowed
            if request_channel_allowed is None:
                return await ctx.send(
                    f"No requests allowed channel found. Please set one on the configuration."
                )
            if request_channel is None:
                return await ctx.send(
                    f"No requests channel found. Please set one on the configuration."
                )

            temp_request_channel_allowed_name = []
            for temp_channel_id in request_channel_allowed:
                temp_channel = self.bot.get_channel(temp_channel_id)
                if temp_channel:
                    temp_request_channel_allowed_name.append(temp_channel)
            request_channel_allowed_name = [
                f"{channel.name}" for channel in temp_request_channel_allowed_name
            ]
            request_channel_allowed_clean = ", ".join(
                request_channel_allowed_name
            )

            if ctx.message.channel.id not in request_channel_allowed:
                # Tries to let user know in DM that cmd not allowed in that channel, if that fails send in channel.
                # Next tries to delete calling command to reduce spam
                try:
                    await ctx.message.author.send(
                        f"This command can only be used in the channels: {request_channel_allowed_clean} \n\n >>> {request_body[:1850]}"
                    )
                except discord.errors.Forbidden:
                    await ctx.send(
                        f"This command can only be used in the channels: {request_channel_allowed_clean}"
                    )
                try:
                    await ctx.message.delete()
                except discord.errors.Forbidden:
                    pass
                # Stop processing command if not done in right channel
                return

            # Create the embed of info
            embed = discord.Embed(
                color=0x14738E,
                title=f"Port Request from {ctx.message.author} ({ctx.message.author.id})",
                description=f">>> {request_body[:1900]}",
                timestamp=datetime.utcnow(),
            )

            embed.set_footer(
                text=f"Usage: '{ctx.prefix}idea your idea' in {request_channel_allowed_clean}"
            )

            channel = ctx.message.guild.get_channel(request_channel)
            if channel:
                try:
                    msg = await channel.send(embed=embed)

                    upvote = self.bot.get_emoji(self.bot.constants.reactions["upvote"])
                    downvote = self.bot.get_emoji(
                        self.bot.constants.reactions["downvote"]
                    )

                    # Add the reactions
                    for emoji in (upvote, downvote):
                        if emoji:
                            await msg.add_reaction(emoji)
                    # Now let user know it was posted - but if it's in same channel it's being posted to, no need
                    if ctx.message.channel.id == channel.id:
                        # Delete the request command, no feedback
                        try:
                            await ctx.message.delete()
                        except discord.errors.Forbidden:
                            pass
                    else:
                        await ctx.send(
                            f"Thank you for your request, it has now been posted and is available in {channel.mention}"
                        )
                    # Now let's log it to the database
                    try:
                        # Check if there is a user in the database already
                        db_user = (
                            session.query(models.User)
                            .filter(models.User.discord_id == ctx.message.author.id)
                            .first()
                        )
                        # If no DB record for the user then create one
                        if not db_user:
                            db_user = models.User(discord_id=ctx.message.author.id)
                            session.add(db_user)
                        # Check if there is a guild in the database already
                        db_guild = (
                            session.query(models.Server)
                            .filter(models.Server.discord_id == msg.guild.id)
                            .first()
                        )
                        if not db_guild:
                            db_guild = await self.bot.helpers.db_add_new_guild(
                                session, msg.guild.id
                            )

                        new_record = models.Requests(
                            user=db_user,
                            server=db_guild,
                            message_id=msg.id,
                            text=request_body,
                        )
                        session.add(new_record)
                        session.commit()
                    except DBAPIError as err:
                        self.bot.log.exception(
                            f"Error processing database query for '{ctx.command}' command. {sys.exc_info()[0].__name__}: {err}"
                        )
                        session.rollback()
                    except Exception as err:
                        self.bot.log.exception(
                            f"Unknown Error logging to database for to '{ctx.command}' command via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
                        )
                    finally:
                        session.close()
                except discord.errors.Forbidden:
                    await ctx.send(
                        f"Sorry, I lack permissions to be able to submit that request"
                    )
                except Exception as err:
                    self.bot.log.exception(
                        f"Error responding to {ctx.command} via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
                    )
                    try:
                        await ctx.send(
                            f"Error processing {ctx.command}. Error has already been reported to my developers."
                        )
                    except discord.errors.Forbidden:
                        pass

        except discord.HTTPException as err:
            self.bot.log.exception(
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
    bot.add_cog(Request(bot))
