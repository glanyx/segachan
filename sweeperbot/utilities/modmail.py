import io
import sys
from datetime import datetime

import discord
from discord.ext import commands
from num2words import num2words
from sqlalchemy.exc import DBAPIError

from sweeperbot.cogs.utils.paginator import FieldPages
from sweeperbot.db import models
from sweeperbot.utilities.helpers import set_sentry_scope


class ModMail(commands.Cog):
    def __init__(self, bot):
        self.mm_guild = None
        self.main_guild = None
        self.bot = bot
        self.modmail_server_id = None
        self.redis = self.bot.helpers.redis
        # Set the cooldown for Mod Mail
        settings = self.bot.cooldown_settings.get("modmail_incoming")
        message_rate = settings.message_rate
        cooldown_time = settings.cooldown_time
        self._cd_modmail_incoming = commands.CooldownMapping.from_cooldown(
            message_rate, cooldown_time, commands.BucketType.user
        )
        self.bot.log.debug(
            f"ModMail Cooldown set to {message_rate} msgs per {cooldown_time} sec"
        )
        session = self.bot.helpers.get_db_session()
        try:
            # Get guild settings based on the bot ID
            # Theoretically there should only be one mod mail server per bot, if there is more than one, we're fucked.
            guild_settings = (
                session.query(models.ServerSetting)
                .join(models.Server)
                .filter(
                    models.ServerSetting.bot_id == self.bot.user.id,
                    models.ServerSetting.modmail_server_id is not None,
                )
                .first()
            )
            if not guild_settings:
                return
            self.modmail_server_id = guild_settings.modmail_server_id
            # Get the unanswered and in progress categories
            self.modmail_unanswered_cat = self.bot.get_channel(
                guild_settings.modmail_unanswered_cat_id
            )
            self.modmail_in_progress_cat = self.bot.get_channel(
                guild_settings.modmail_in_progress_cat_id
            )
            # Get the mod mail guild, error if none set
            if self.modmail_server_id is None:
                raise ValueError("No Mod Mail Guild found, MM not initialized")
            self.mm_guild = self.bot.get_guild(self.modmail_server_id)
            self.db_mm_guild = (
                session.query(models.Server)
                .filter(models.Server.discord_id == self.modmail_server_id)
                .first()
            )
            # Get the main guild
            guild_id = (
                session.query(models.Server)
                .filter(models.Server.id == guild_settings.server_id)
                .first()
            ).discord_id
            self.main_guild = self.bot.get_guild(guild_id)

            # Now that we have most stuff initialized, let's do an inventory of all mod mail channels and purge from the
            # redis cache that doesn't have a matching channel
            if self.mm_guild:
                self.clean_redis_cache()

        except DBAPIError as err:
            self.bot.log.exception(
                f"Error processing database query for getting mod mail settings. {sys.exc_info()[0].__name__}: {err}"
            )
            session.rollback()
        except Exception as err:
            self.bot.log.exception(
                f"Unknown exception initializing mod mail utility. {sys.exc_info()[0].__name__}: {err}"
            )
        finally:
            session.close()

    def clean_redis_cache(self):
        self.bot.log.info(f"Mod Mail: Starting Redis Cache Cleaning")
        # We're assuming the channel was deleted on the server while the bot was offline
        # We don't have a user messaging in, so all we have is the bot ID and channel ID's that DO exist

        # Let's get all the redis keys that match this bot
        keys = list(self.redis.keys(pattern=f"user_id:bid:{self.bot.user.id}:mmcid:*"))
        # Now let's get all channel ID's in the mod mail guild
        channels = self.mm_guild.channels

        # Now let's iterate through all the guild channels and see if we can find a redis key that matches:
        for channel in channels:
            temp_key = f"user_id:bid:{self.bot.user.id}:mmcid:{channel.id}"
            if temp_key in keys:
                # If the redis key exists, remove it from the list of keys. This means the channel still exists, and
                # we still need the key
                keys.remove(temp_key)

        # Now that the list of keys is down to those that do not have a matching channel in the guild, we can remove
        # those keys from the redis cache
        # For cleaning up, we first need to get the user id the deleted channel belongs to
        for key in keys:
            # Get the user ID from the key
            user_id = self.redis.get(key)

            # Then we can delete the redis cache for that channel
            result = self.redis.delete(
                f"mm_chanid:bid:{self.bot.user.id}:uid:{user_id}"
            )
            if result:
                self.bot.log.info(
                    f"Mod Mail: Deleted Orphaned Key 'mm_chanid:bid:{self.bot.user.id}:uid:{user_id}'"
                )
            del result

            # Now that the cache for the channel associated with that user is deleted we can delete the user cache
            result = self.redis.delete(key)
            if result:
                self.bot.log.info(f"Mod Mail: Deleted Orphaned Key '{key}'")

    # Handles any mod mail messages either sent to the bot or in the mod mail server
    @commands.Cog.listener("on_message")
    async def modmail_on_message(self, message):
        # If modmail is not enabled, skip it all
        if not self.modmail_server_id:
            return

        # If message is a command, then ignore it
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        # Checks if the message is by the bot, and if so return - we don't want to handle these type of messages
        if message.author.id == self.bot.user.id:
            return

        # If message is from a DM, then handle an incoming message event
        if isinstance(message.channel, discord.DMChannel) and (
            self.main_guild and self.modmail_server_id
        ):
            await self.handle_incoming_dm_from_user(ctx, message)
        # If message is from the Mod Mail server, handle an outgoing message event
        elif (
            isinstance(message.channel, discord.TextChannel)
            and message.guild.id == self.modmail_server_id
        ):
            await self.handle_outgoing_chan_from_mod(message)

    async def handle_incoming_dm_from_user(self, ctx, message):
        self.bot.log.debug(
            f"ModMail: New Message From: {message.author} ({message.author.id})"
        )
        # If the user is blacklisted, exit out
        if await self.bot.helpers.check_if_blacklisted(
            message.author.id, self.modmail_server_id
        ):
            self.bot.log.debug(
                f"ModMail: User {message.author} ({message.author.id}) Blacklisted, unable to use Mod Mail"
            )
            return
        # Check if user is on cooldown/rate limited
        # Also check if the antispam modmail quickmsg feature is enabled
        settings = self.bot.guild_settings.get(self.main_guild.id)
        if settings and settings.antispam_quickmsg_modmail:
            bucket = self._cd_modmail_incoming.get_bucket(message)
            retry_after = bucket.update_rate_limit()
            if retry_after:
                # you're rate limited helpful message here
                self.bot.log.debug(
                    f"ModMail: User {message.author} ({message.author.id}) is on cooldown/rate limited, unable to use Mod Mail. Expires: {retry_after:0.2f} seconds"
                )
                await message.channel.send(
                    f"You are currently on cooldown. Please decrease the rate at which you send us messages or you may find yourself blacklisted.\n\nYou may send messages again in {retry_after:0.2f} seconds."
                )
                return
        # you're not rate limited, continue

        new_channel_created = False
        # Check if we have a channel in the mod mail server yet
        mm_channel_id = self.redis.get(
            f"mm_chanid:bid:{self.bot.user.id}:uid:{message.author.id}"
        )
        self.bot.log.debug(
            f"ModMail: Redis mm_channel_id: {mm_channel_id} User: {message.author} ({message.author.id})"
        )
        # Try to get the channel
        mm_channel = None
        if mm_channel_id:
            mm_channel = self.bot.get_channel(int(mm_channel_id))
        # If no channel, create one
        if not mm_channel:
            mm_channel = await self.make_modmail_channel(message.author)
            # Additional check to make sure a mod mail channel exists
            if not mm_channel:
                self.bot.log.exception(
                    f"ModMail: We just made a mod mail channel, why are we saying there isn't one for user: ({message.author.id})"
                )
                return
            # When we get an incoming message we know all 3 parts:
            # 1. The bot ID
            # 2. The mod mail channel ID
            # 3. The users ID
            # We take all this info and store it, so when we get an incoming message we know the mod mail channel
            # to send it to. When we have an outgoing message we can find the user ID as at any given point
            # we know 2 parts and need to find the 3rd.
            #
            # This sets the mod mail channel ID with a key of the bot ID and the author ID
            # TO DO - Could move the redis cache setting into self.make_modmail_channel so it happens upon creation
            self.redis.set(
                f"mm_chanid:bid:{self.bot.user.id}:uid:{message.author.id}",
                f"{mm_channel.id}",
            )
            self.bot.log.debug(
                f"ModMail: Redis SET: 'mm_chanid:bid:{self.bot.user.id}:uid:{message.author.id}' TO '{mm_channel.id}'"
            )
            # This sets the users ID with a key of the bot ID and the mod mail channel ID
            self.redis.set(
                f"user_id:bid:{self.bot.user.id}:mmcid:{mm_channel.id}",
                f"{message.author.id}",
            )
            self.bot.log.debug(
                f"ModMail: Redis SET: 'user_id:bid:{self.bot.user.id}:mmcid:{mm_channel.id}' TO '{message.author.id}'"
            )
            new_channel_created = True

        # Now that we have the channel, we need to process it
        session = self.bot.helpers.get_db_session()
        try:
            # Step 2: Get the users history and send it:
            (
                embed_result_entries,
                footer_text,
            ) = await self.bot.helpers.get_action_history(
                session, message.author, self.main_guild
            )

            p = FieldPages(
                ctx, per_page=8, entries=embed_result_entries, mm_channel=mm_channel,
            )
            p.embed.color = 0xFF8C00
            p.embed.set_author(
                name=f"Member: {message.author} ({message.author.id})",
                icon_url=message.author.avatar_url,
            )
            p.embed.set_footer(text=footer_text)

            # Step 3: Send the users message to the mod mail channel
            msg_body = message.clean_content[:2000]
            embed = discord.Embed(
                color=0x19D219, timestamp=datetime.utcnow(), description=msg_body
            )
            embed.set_author(
                name=f"Member: {message.author} ({message.author.id})",
                icon_url=message.author.avatar_url,
            )
            file_links = []
            if message.attachments:
                all_links = []
                counter = 0
                for file in message.attachments:
                    counter += 1
                    word = num2words(counter)
                    link = f"Link [{word}]({file.url})"
                    all_links.append(link)
                    file_links.append(file.url)
                attachments_text = ", ".join(all_links)
                embed.add_field(
                    name="Attachments", value=f"{attachments_text}", inline=False
                )
            embed.add_field(
                name="Bot/User Channel ID", value=f"{message.channel.id}", inline=False
            )
            embed.add_field(
                name="Bot/User Message ID", value=f"{message.id}", inline=False
            )
            # Set the footer
            embed.set_footer(text=f"Incoming Mod Mail")
            # If this is a new interaction (defined by having to create a new channel in the mod mail server)
            if new_channel_created:
                # Send the history
                try:
                    await p.paginate(modmail_bypass=True)
                except discord.errors.HTTPException:
                    self.bot.log.error(
                        f"Error sending History in Mod Mail for {message.author.id}"
                    )
                # Let the user know that we will use reactions to signify their message was received
                await message.channel.send(self.bot.constants.modmail_read_receipts)
            # Always send the users message to us
            await mm_channel.send(embed=embed)
            # Step 4: Let the user know we received their message
            await message.add_reaction("✉")
            # Step 5: Log to the database
            # Check if there is a user in the database already
            db_user = (
                session.query(models.User)
                .filter(models.User.discord_id == message.author.id)
                .first()
            )
            # If no DB record for the user then create one
            if not db_user:
                db_user = models.User(discord_id=message.author.id)
                session.add(db_user)
            # Get the mod mail guild
            db_mm_guild = (
                session.query(models.Server)
                .filter(models.Server.discord_id == self.mm_guild.id)
                .first()
            )
            # Get the main guild
            db_main_guild = (
                session.query(models.Server)
                .filter(models.Server.discord_id == self.main_guild.id)
                .first()
            )
            # Create the data to inject
            data = {
                "mm_channel_id": mm_channel.id,
                "user_channel_id": message.channel.id,
                "message_id": message.id,
                "message": msg_body,
                "from_mod": False,
                "file_links": file_links,
            }
            new_message = models.ModMailMessage(
                primary_server=db_main_guild,
                mm_server=db_mm_guild,
                user=db_user,
                **data,
            )
            session.add(new_message)
            session.commit()

        except DBAPIError as err:
            self.bot.log.exception(
                f"Error processing database query for an incoming mod mail. {sys.exc_info()[0].__name__}: {err}"
            )
            session.rollback()
        except Exception as err:
            self.bot.log.exception(
                f"Unknown exception processing incoming mod mail. {sys.exc_info()[0].__name__}: {err}"
            )
            await message.channel.send(
                f"There was an error processing your mod mail. Please wait a few minutes and try again. If you are still having issues, contact a mod directly."
                f"\n\nThis error has already been reported to my developers. Sorry for the inconvenience."
            )
        finally:
            session.close()

    async def handle_outgoing_chan_from_mod(self, message):
        user = None
        # Check if we have a user for the mod mail channel the message is being sent in
        user_id = self.redis.get(
            f"user_id:bid:{self.bot.user.id}:mmcid:{message.channel.id}"
        )
        # If no user ID, such as message sent in a non user mod mail channel, just stop processing
        if not user_id:
            return
        # Try to get the user from the bots caching
        else:
            user = self.bot.get_user(int(user_id))
            # Try to get from an API call
            if not user:
                user = await self.bot.fetch_user(int(user_id))
                # If no user, let mods know, stop processing
                if not user:
                    self.bot.log.exception(
                        f"Unable to find a user from the User ID: {user_id}. This could be due to bad Redis cache data.\n\n**Redis Data:** 'user_id:bid:{self.bot.user.id}:mmcid:{message.channel.id}'"
                    )
                    return await message.channel.send(
                        f"Unable to find a user from the User ID: {user_id}. Please validate it's the correct User ID for the user. This has already been reported to my developers."
                    )

        # If the user is blacklisted, exit out (but let's tell the mods first)
        if await self.bot.helpers.check_if_blacklisted(user.id, self.modmail_server_id):
            self.bot.log.debug(
                f"User {message.author} ({message.author.id}) Blacklisted, unable to use Mod Mail"
            )
            return await message.channel.send(
                "\N{CROSS MARK} Sorry, unable to send to that user as they are **blacklisted.**"
            )

        # Now that we have the channel, we need to process it
        session = self.bot.helpers.get_db_session()
        try:
            msg_body = f"{message.content[:1900]}\n\n-{message.author}"

            # Step 1: Send the mods message to the user
            if message.attachments:
                all_links = []
                for file in message.attachments:
                    new_file = discord.File(
                        io.BytesIO(await file.read()), filename=file.filename
                    )
                    all_links.append(new_file)
                # Once we have all files, send to the user
                msg_to_user = await user.send(msg_body, files=all_links)
            else:
                # If no attachments send regular message
                msg_to_user = await user.send(msg_body)

            # Step 2: Send the message to the mod server
            embed = discord.Embed(
                color=0x551A8B, timestamp=datetime.utcnow(), description=msg_body
            )
            embed.set_author(
                name=f"Member: {message.author} ({message.author.id})",
                icon_url=message.author.avatar_url,
            )
            # Create list of links
            file_links = []
            if msg_to_user.attachments:
                all_links = []
                counter = 0
                for file in msg_to_user.attachments:
                    counter += 1
                    word = num2words(counter)
                    link = f"Link [{word}]({file.proxy_url})"
                    all_links.append(link)
                    file_links.append(file.proxy_url)
                attachments_text = ", ".join(all_links)
                embed.add_field(
                    name="Attachments", value=f"{attachments_text}", inline=False
                )
            embed.add_field(
                name="Bot/User Channel ID", value=f"{user.dm_channel.id}", inline=False
            )
            embed.add_field(
                name="Bot/User Message ID", value=f"{msg_to_user.id}", inline=False
            )
            # Set the footer
            embed.set_footer(text=f"Outgoing Mod Mail")

            # Send the message in the channel
            await message.channel.send(embed=embed)
            # If message successfully sends, delete the calling message
            await message.delete()
            # Step 3: Move to the In Progress category, only if it was in unanswered
            if message.channel.category_id == self.modmail_unanswered_cat.id:
                try:
                    await message.channel.edit(category=self.modmail_in_progress_cat)
                except discord.errors.HTTPException as err:
                    if err.code == 50035:
                        self.bot.log.warning(f"Unable to move channel. Error: {err}")

                # Update category counts
                # 2020/06/19 - Disabling Category Count Update due to B9940-121
                # await self.update_cat_count(
                #    self.modmail_unanswered_cat, unanswered=True
                # )
                # await self.update_cat_count(
                #    self.modmail_in_progress_cat, unanswered=False
                # )
            # Step 4: Log to the database
            # Check if there is a user in the database already
            db_user = (
                session.query(models.User)
                .filter(models.User.discord_id == message.author.id)
                .first()
            )
            # If no DB record for the user then create one
            if not db_user:
                db_user = models.User(discord_id=message.author.id)
                session.add(db_user)
            # Get the mod mail guild
            db_mm_guild = (
                session.query(models.Server)
                .filter(models.Server.discord_id == self.mm_guild.id)
                .first()
            )
            # Get the main guild
            db_main_guild = (
                session.query(models.Server)
                .filter(models.Server.discord_id == self.main_guild.id)
                .first()
            )
            # Create the data to inject
            data = {
                "mm_channel_id": message.channel.id,
                "user_channel_id": user.dm_channel.id,
                "message_id": msg_to_user.id,
                "message": msg_body,
                "from_mod": True,
                "file_links": file_links,
            }
            new_message = models.ModMailMessage(
                primary_server=db_main_guild,
                mm_server=db_mm_guild,
                user=db_user,
                **data,
            )
            session.add(new_message)
            session.commit()

        except DBAPIError as err:
            self.bot.log.exception(
                f"Error processing database query for outgoing mod mail. {sys.exc_info()[0].__name__}: {err}"
            )
            session.rollback()
        except discord.Forbidden:
            await message.channel.send(
                f"Unable to send messages to this user. They may have blocked the bot or don't share any servers with the bot anymore."
            )
        except Exception as err:
            self.bot.log.exception(
                f"Unknown exception processing outgoing mod mail. {sys.exc_info()[0].__name__}: {err}"
            )
            await message.channel.send(
                f"There was an error processing the outgoing mod mail. Please wait a few minutes and try again. If you are still having issues, please contact the bot developers."
                f"\n\nThis error has already been reported to my developers. Sorry for the inconvenience."
            )
        finally:
            session.close()

    async def make_modmail_channel(self, author):
        try:
            # Normalize the name without the discriminator
            name_temp = self.bot.helpers.normal_name(author.name)
            if len(name_temp) == 0:
                name_temp = "unicode"
            # Create the name normalized with the discrim
            name_normal = f"{name_temp}-{author.discriminator}"
            # Create the channel
            new_channel = await self.modmail_unanswered_cat.create_text_channel(
                name=name_normal, topic=f"Member: {author.id}"
            )
            self.bot.log.debug(f"ModMail: Created channel for {author} ({author.id})")
            # Update category name with count
            # 2020/06/19 - Disabling Category Count Update due to B9940-121
            # await self.update_cat_count(self.modmail_unanswered_cat, unanswered=True)
            return new_channel
        except Exception as err:
            self.bot.log.exception(
                f"ModMail: Unknown exception creating new mod mail channel. {sys.exc_info()[0].__name__}: {err}"
            )
            return None

    async def update_cat_count(self, category, unanswered):
        # Sets count to None in an attempt to clear it each time
        count = None
        try:
            count = 0
            for channel in category.text_channels:
                count += 1
            self.bot.log.debug(f"ModMail: {category.name}: Count: {count}")
            if unanswered:
                cat_type = "Unanswered"
            else:
                cat_type = "In Progress"
            await category.edit(name=f"{cat_type} {count}/50")
            self.bot.log.debug(
                f"ModMail: Updated Cat Counts: New Name: {cat_type} {count}/50"
            )
        except Exception as err:
            self.bot.log.exception(
                f"ModMail: Unknown exception updating category count. {sys.exc_info()[0].__name__}: {err}"
            )
        finally:
            # Deletes count variable in an attempt to clear it each time
            del count

    # TO DO - Create mod mail logging (embed, channel "modmail-logs")
    async def log_modmails(self, mm_channel_id, user_id, deleted):
        # Log when a mod mail channel is created or deleted
        pass

    @commands.Cog.listener("on_guild_channel_delete")
    async def cleanup_deleted_channels(self, channel):
        # While we check on_message if mod mail is enabled and skip if not, we're going to process all mod mail
        # channel deletes to make sure our redis cache is clean and doesn't have any orphaned data

        # If the channel deleted was not from the mod mail server, skip it
        if not channel.guild.id == self.modmail_server_id:
            return

        # For cleaning up, we first need to get the user id the deleted channel belongs to
        user_id = self.redis.get(f"user_id:bid:{self.bot.user.id}:mmcid:{channel.id}")

        # Then we can delete the redis cache for that channel
        result = self.redis.delete(f"mm_chanid:bid:{self.bot.user.id}:uid:{user_id}")
        if result:
            self.bot.log.debug(
                f"Mod Mail: Deleted Key 'mm_chanid:bid:{self.bot.user.id}:uid:{user_id}'"
            )
        del result

        # Now that the cache for the channel associated with that user is deleted we can delete the user cache
        result = self.redis.delete(f"user_id:bid:{self.bot.user.id}:mmcid:{channel.id}")
        if result:
            self.bot.log.debug(
                f"Mod Mail: Deleted Key 'user_id:bid:{self.bot.user.id}:mmcid:{channel.id}'"
            )

        # Now that the channel is purged in the system, update the counts for the categories
        # 2020/06/19 - Disabling Category Count Update due to B9940-121
        # await self.update_cat_count(self.modmail_in_progress_cat, unanswered=False)
        # await self.update_cat_count(self.modmail_unanswered_cat, unanswered=True)

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def mm(self, ctx, user_id: str):
        """Takes a user ID and creates a Mod Mail channel to allow you to message the user.

        Requires Permission: Manage Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_id: str
            The User ID of the user the Mod Mail is being created for.
        """
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            if not self.modmail_server_id:
                return await ctx.send(f"It looks like Mod Mail is not setup yet.")

            if user_id:
                # We do not pass a guild as this person shouldn't be in the mod mail server unless a mod/special guest
                member = await self.bot.helpers.get_member_or_user(user_id)
                if not member:
                    return await ctx.send(
                        f"Unable to find the requested user. Please make sure the user ID is valid."
                    )
            else:
                return await ctx.send(
                    f"A user ID or Mention must be provided for who to mute."
                )

            # Now that we have a user, let's create the mod mail needed.
            if (
                isinstance(ctx.message.channel, discord.TextChannel)
                and ctx.message.guild.id == self.modmail_server_id
            ):
                self.bot.log.debug(
                    f"ModMail: Creating new MM for: {member} ({member.id})"
                )
                new_channel_created = False
                # Check if we have a channel in the mod mail server yet
                mm_channel_id = self.redis.get(
                    f"mm_chanid:bid:{self.bot.user.id}:uid:{member.id}"
                )
                self.bot.log.debug(
                    f"ModMail: Redis mm_channel_id: {mm_channel_id} User: {member} ({member.id})"
                )
                # Try to get the channel
                mm_channel = None
                if mm_channel_id:
                    mm_channel = self.bot.get_channel(int(mm_channel_id))
                # If no channel, create one
                if not mm_channel:
                    mm_channel = await self.make_modmail_channel(member)
                    # Additional check to make sure a mod mail channel exists
                    if not mm_channel:
                        return await ctx.send(
                            f"Unable to find the mod mail channel that was created for the user {member} ({member.id}). Please try again."
                        )

                    # This sets the mod mail channel ID with a key of the bot ID and the author ID
                    self.redis.set(
                        f"mm_chanid:bid:{self.bot.user.id}:uid:{member.id}",
                        f"{mm_channel.id}",
                    )
                    # This sets the users ID with a key of the bot ID and the mod mail channel ID
                    self.redis.set(
                        f"user_id:bid:{self.bot.user.id}:mmcid:{mm_channel.id}",
                        f"{member.id}",
                    )
                    self.bot.log.debug(
                        f"ModMail: Redis SET: 'mm_chanid:bid:{self.bot.user.id}:uid:{member.id}' TO '{mm_channel.id}'"
                    )
                    self.bot.log.debug(
                        f"ModMail: Redis SET: 'user_id:bid:{self.bot.user.id}:mmcid:{mm_channel.id}' TO '{member.id}'"
                    )
                    new_channel_created = True

                    # Now let's populate the new channel with the history
                    session = self.bot.helpers.get_db_session()
                    try:
                        # Get the users history:
                        (
                            embed_result_entries,
                            footer_text,
                        ) = await self.bot.helpers.get_action_history(
                            session, member, self.main_guild
                        )

                        p = FieldPages(
                            ctx,
                            per_page=8,
                            entries=embed_result_entries,
                            mm_channel=mm_channel,
                        )
                        p.embed.color = 0xFF8C00
                        p.embed.set_author(
                            name=f"Member: {member} ({member.id})",
                            icon_url=member.avatar_url,
                        )
                        p.embed.set_footer(text=footer_text)

                        # If this is a new interaction (defined by having to create new channel in the mod mail server)
                        if new_channel_created:
                            # Send the history
                            try:
                                await p.paginate(modmail_bypass=True)
                            except discord.errors.HTTPException:
                                self.bot.log.error(
                                    f"Error sending History in Mod Mail for {member.id}"
                                )
                    except DBAPIError as err:
                        self.bot.log.exception(
                            f"ModMail: Database Error getting user history. {sys.exc_info()[0].__name__}: {err}"
                        )
                        session.rollback()
                    except Exception as err:
                        self.bot.log.exception(
                            f"ModMail: Error getting user history. {sys.exc_info()[0].__name__}: {err}"
                        )
                    finally:
                        session.close()

                await ctx.send(
                    f"The following Mod Mail channel is now ready for use:\n\n**Channel:** {mm_channel.mention}\n**For User:** {member} ({member.id})"
                )

        except discord.HTTPException as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Discord HTTP Error responding to {ctx.command}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except Exception as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Error responding to {ctx.command}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )


def setup(bot):
    bot.add_cog(ModMail(bot))
