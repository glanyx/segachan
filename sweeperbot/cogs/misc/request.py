import asyncio
import sys
from datetime import datetime

import discord
from discord.ext import commands
from sqlalchemy.exc import DBAPIError

from sweeperbot.db import models


class Request(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["requestport", "rq", "rqp"])
    @commands.has_permissions(send_messages=True)
    @commands.guild_only()
    async def request(self, ctx, *, request_body):
        """Takes input as a request and reposts it in a dedicated channel and provides voting reactions to show interest. Logs to database for record keeping. Detects duplication.

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

            upvote_emoji = settings.upvote_emoji or self.bot.constants.reactions["upvote"]
            downvote_emoji = settings.downvote_emoji or self.bot.constants.reactions["downvote"]
            question_emoji = settings.question_emoji or self.bot.constants.reactions["question"]
            downvotes_allowed = settings.allow_downvotes
            questions_allowed = settings.allow_questions

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

            # Check if request exists
            guild_requests = (
                session.query(models.Requests)
                .join(models.Server, models.Server.id == models.Requests.server_id)
                .filter(models.Server.discord_id == ctx.message.guild.id)
                .all()
            )

            # Check for direct duplicates
            if request_body[:1900].lower() in [singleRequest.text.lower() for singleRequest in guild_requests]:
                for singleRequest in guild_requests:
                    title = getattr(singleRequest, "text")

                    if request_body[:1900].lower() == title.lower():

                        dupe_link = getattr(singleRequest, "message_id")
                        await ctx.message.delete()

                        dupe_embed = discord.Embed(
                            color=0x00CC00,
                            title="Found it!",
                            description=f"It looks like a request for this title already exists! You can view the existing request [here](https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{dupe_link}).\nRemember to upvote it!",
                            timestamp=datetime.utcnow(),
                        ).set_footer(
                            text="This message will be removed in 15 seconds."
                        )

                        await (await ctx.channel.send(embed=dupe_embed)).delete(delay=15)
                        return

            # Loop through existing requests
            for singleRequest in guild_requests:
                game_title = getattr(singleRequest, "text")
                message_link = getattr(singleRequest, "message_id")

                # Check for substrings in the text
                if (
                    request_body[:1900].lower() in game_title.lower()
                    or game_title.lower() in request_body[:1900].lower()
                ):
                    
                    # Check function for reactions (yes / no)
                    def check(reaction, user):
                        return user == ctx.author and (
                            reaction.emoji == self.bot.get_emoji(self.bot.constants.reactions["yes"])
                            or reaction.emoji == self.bot.get_emoji(self.bot.constants.reactions["no"])
                        )

                    # Embed to display when a potential duplicate entry is found
                    found_embed = discord.Embed(
                        color=0xFFA500,
                        title="I've found an existing request quite similar to yours! Is this the title you wanted to request?",
                        description=f">>> {game_title}",
                        timestamp=datetime.utcnow(),
                    ).set_footer(
                        text="This message will timeout in 60 seconds and your request will be removed without a response."
                    )

                    msg = await ctx.channel.send(embed=found_embed)

                    # Reactions for the user to react on
                    yes = self.bot.get_emoji(self.bot.constants.reactions["yes"])
                    no = self.bot.get_emoji(self.bot.constants.reactions["no"])

                    # Add the reactions
                    for emoji in (yes, no):
                        if emoji:
                            await msg.add_reaction(emoji)

                    try:
                        # Wait for the user to confirm or deny if duplicate
                        reaction, user = await self.bot.wait_for("reaction_add", check=check, timeout=60.0)
                    except asyncio.TimeoutError:
                        # Delete message on timeout
                        await msg.delete()
                        await ctx.message.delete()
                        return
                    else:
                        # Delete message on reaction
                        await msg.delete()
                        # If user replies yes, link to the existing request
                        if reaction.emoji == self.bot.get_emoji(self.bot.constants.reactions["yes"]):
                            await ctx.message.delete()

                            existing_embed = discord.Embed(
                                color=0x00CC00,
                                title="Found it!",
                                description=f"Great! You can view the existing request [here](https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{message_link}).\nRemember to upvote it!",
                                timestamp=datetime.utcnow(),
                            ).set_footer(
                                text="This message will be removed in 15 seconds."
                            )

                            await (await ctx.channel.send(embed=existing_embed)).delete(delay=15)
                            return
                      

            # Create the embed of info
            embed = discord.Embed(
                color=0x14738E,
                title=f"Port Request from {ctx.message.author} ({ctx.message.author.id})",
                description=f">>> {request_body[:1900]}",
                timestamp=datetime.utcnow(),
            )

            embed.set_footer(
                text=f"Usage: '{ctx.prefix}request [your game]' in {request_channel_allowed_clean}"
            )

            channel = ctx.message.guild.get_channel(request_channel)
            if channel:
                try:
                    msg = await channel.send(embed=embed)

                    upvote = self.bot.get_emoji(upvote_emoji)
                    downvote = self.bot.get_emoji(downvote_emoji) if downvotes_allowed else None
                    question = self.bot.get_emoji(question_emoji) if questions_allowed else None

                    # Add the reactions
                    for emoji in (upvote, downvote, question):
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
                        await ctx.message.delete()
                        await (await ctx.send(
                            f"Thank you for your request, it has now been posted and is available in {channel.mention}"
                        )).delete(delay=15)
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
