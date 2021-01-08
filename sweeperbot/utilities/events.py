import io
import sys
from datetime import datetime

import aiohttp
import discord
from discord.ext import commands
from sqlalchemy.exc import DBAPIError, IntegrityError

from sweeperbot.db import models


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    

    @commands.Cog.listener()
    async def on_member_join(self, member):
        session = self.bot.helpers.get_db_session()
        try:
            # If the member joining is this bot then skip trying to log
            if self.bot.user.id == member.id or member.bot:
                return

            # Get guild settings
            guild = member.guild
            settings = await self.bot.helpers.get_one_guild_settings(session, guild.id)
            # If welcome message enabled, send DM to user
            if settings.welcome_msg_enabled and settings.welcome_msg:
                try:
                    # Format the welcome message
                    action_type = "Message"
                    message = self.bot.constants.infraction_header.format(
                        action_type=action_type.lower(), guild=guild
                    )
                    # Reduces the text to 1,800 characters to leave enough buffer for header and footer text
                    message += f"{settings.welcome_msg[:1800]}"
                    # Set footer based on if the server has modmail or not
                    if settings.modmail_server_id:
                        message += self.bot.constants.footer_with_modmail.format(
                            guild=guild
                        )
                    else:
                        message += self.bot.constants.footer_no_modmail.format(
                            guild=guild
                        )
                    # Send the message
                    await member.send(message)
                except discord.Forbidden:
                    # Unable to DM user, likely privacy settings disallows, we can't do anything about it so ignore
                    pass
                except Exception as err:
                    self.bot.log.error(
                        f"Error sending welcome message to user {member} ({member.iod}). {sys.exc_info()[0].__name__}: {err}"
                    )
            # If join role set, add to user
            if settings.on_join_role_enabled and settings.on_join_role_id:
                try:
                    role = member.guild.get_role(settings.on_join_role_id)
                    if role:
                        await member.add_roles(role)
                except Exception as err:
                    self.bot.log.error(
                        f"Error adding on join role to user {member} ({member.iod}). {sys.exc_info()[0].__name__}: {err}"
                    )
            # Log new user to the database
            # First check if they exist in our DB already
            dbuser = (
                session.query(models.User)
                .filter(models.User.discord_id == member.id)
                .first()
            )
            # If they don't exist in the database
            if not dbuser:
                # Add them to the database
                dbuser = models.User(discord_id=member.id)
                session.add(dbuser)
            # Also add an initial alias for them
            # While this will cause some duplicate records as they join multiple servers the bot is in without an alias
            # change, this will be preferred so we always know their name, instead if they join when bot knows them as
            # one name, then they leave the servers the bot watches, changes them, and rejoins we don't know their new
            # name, thus making it harder to pull reports for spam abuse based on name
            # TO DO - Find the latest entry by a user with that user ID and if the name matches, skip it
            new_alias = models.Alias(name=f"{member}", user=dbuser)
            # Add the new_alias to the session to log to the database
            session.add(new_alias)
            try:
                session.commit()
            except IntegrityError as err:
                self.bot.log.error(
                    f"Duplicate Database Entry Error logging Member Join to database. {sys.exc_info()[0].__name__}: {err}"
                )
                session.rollback()

            # Try and get the temp logs channel
            logs = discord.utils.get(guild.text_channels, name="member-logs-temp")

            if not logs:
                # If there is no temp logs channel, try the normal logs channel
                logs = discord.utils.get(guild.text_channels, name="member-logs")
                # Lastly, try the old inconsistently named log channel
                if not logs:
                    logs = discord.utils.get(guild.text_channels, name="members-log")
                    if not logs:
                        return

            # Checks if the bot can even send messages in that channel
            if not (
                logs.permissions_for(logs.guild.me).send_messages
                and logs.permissions_for(logs.guild.me).embed_links
            ):
                return self.bot.log.debug(
                    f"Missing Permissions to log Member Join in Guild: {logs.guild.id} | Channel: {logs.id}"
                )

            # Guild join date
            guild_join_date = self.bot.helpers.relative_time(
                datetime.utcnow(), member.joined_at, brief=True
            )
            guild_join_date = f"{member.joined_at.replace(microsecond=0)} UTC\n*{guild_join_date} ago*"

            # Discord join date
            discord_join_date = self.bot.helpers.relative_time(
                datetime.utcnow(), member.created_at, brief=True
            )
            discord_join_date = f"{member.created_at.replace(microsecond=0)} UTC\n*{discord_join_date} ago*"

            # Create the embed of info
            embed = discord.Embed(color=0x80F31F, timestamp=datetime.utcnow())
            embed.set_author(name=f"{member} ({member.id})", icon_url=member.avatar_url)
            embed.set_thumbnail(url=member.avatar_url)
            embed.add_field(name="Joined Guild", value=f"{guild_join_date}")
            embed.add_field(name="Joined Discord", value=f"{discord_join_date}")
            embed.set_footer(text="User Joined")

            try:
                await logs.send(embed=embed)
            except discord.Forbidden:
                self.bot.log.warning(
                    f"Missing permissions to send in {logs.name} ({logs.id}) in guild {logs.guild.name} ({logs.guild.id})"
                )
        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error processing Member Join Event. {sys.exc_info()[0].__name__}: {err}"
            )
        except Exception as err:
            self.bot.log.exception(
                f"Error processing Member Join Event. {sys.exc_info()[ 0].__name__}: {err}"
            )
        except DBAPIError as err:
            self.bot.log.exception(
                f"Error logging Member Join to database. {sys.exc_info()[0].__name__}: {err}"
            )
            session.rollback()
        finally:
            session.close()

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        try:
            # If the member leaving is themselves then skip trying to log
            if self.bot.user.id == member.id:
                return
            # Remove any Mod or Admin relationship on member leaving the server
            session = self.bot.helpers.get_db_session()
            try:
                await self.bot.helpers.db_process_mod_relationship(
                    member, session, server_mod=False
                )
                await self.bot.helpers.db_process_admin_relationship(
                    member, session, server_admin=False
                )
                # Commit the changes to the database
                session.commit()
            except IntegrityError:
                self.bot.log.debug(
                    f"Duplicate Server Relationship database record: Guild: {member.guild.id} | User: {member.id}"
                )
                session.rollback()
            except DBAPIError as err:
                self.bot.log.exception(
                    f"Database error logging Server Relationship removal to database. {sys.exc_info()[0].__name__}: {err}"
                )
                session.rollback()
            except Exception as err:
                self.bot.log.exception(
                    f"Generic Error logging Server Relationship removal to database. {sys.exc_info()[0].__name__}: {err}"
                )
                session.rollback()
            finally:
                session.close()

            try:
                # Try and get the temp logs channel
                logs = discord.utils.get(
                    member.guild.text_channels, name="member-logs-temp"
                )

                if not logs:
                    # If there is no temp logs channel, try the normal logs channel
                    logs = discord.utils.get(
                        member.guild.text_channels, name="member-logs"
                    )
                    if not logs:
                        logs = discord.utils.get(
                            member.guild.text_channels, name="members-log"
                        )
                        if not logs:
                            return
            except Exception as err:
                return self.bot.log.exception(
                    f"Error getting logs channel. {sys.exc_info()[0].__name__}: {err}"
                )

            # Checks if the bot can even send messages in that channel
            if not (
                logs.permissions_for(logs.guild.me).send_messages
                and logs.permissions_for(logs.guild.me).embed_links
            ):
                return self.bot.log.debug(
                    f"Missing Permissions to log Member Part in Guild: {logs.guild.id} | Channel: {logs.id}"
                )

            # Guild join date
            guild_join_date = "Unknown"
            if member.joined_at:
                guild_join_date = self.bot.helpers.relative_time(
                    datetime.utcnow(), member.joined_at, brief=True
                )

            guild_join_date = f"{member.joined_at.replace(microsecond=0) if member.joined_at else 'Unknown'} UTC\n*{guild_join_date} ago*"

            # Discord join date
            discord_join_date = "Unknown"
            if member.created_at:
                discord_join_date = self.bot.helpers.relative_time(
                    datetime.utcnow(), member.created_at, brief=True
                )
            discord_join_date = f"{member.created_at.replace(microsecond=0) if member.created_at else 'Unknown'} UTC\n*{discord_join_date} ago*"

            # Create the embed of info
            embed = discord.Embed(color=0xC70000, timestamp=datetime.utcnow())
            embed.set_author(name=f"{member} ({member.id})", icon_url=member.avatar_url)
            embed.set_thumbnail(url=member.avatar_url)
            embed.add_field(name="Joined Guild", value=f"{guild_join_date}")
            embed.add_field(name="Joined Discord", value=f"{discord_join_date}")
            embed.set_footer(text="User Left")

            try:
                await logs.send(embed=embed)
            except discord.Forbidden:
                self.bot.log.warning(
                    f"Missing permissions to send in {logs.name} ({logs.id}) in guild {logs.guild.name} ({logs.guild.id})"
                )
        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error processing Member Part Event. {sys.exc_info()[0].__name__}: {err}"
            )
        except Exception as err:
            self.bot.log.exception(
                f"Error processing Member Part Event. {sys.exc_info()[ 0].__name__}: {err}"
            )
    
    @commands.Cog.listener()
    async def on_message(self, msg):
        # Check if it's from a DM, then ignore it since we're processing this in the mod mail module
        if isinstance(msg.channel, discord.DMChannel):
            pass

        if isinstance(msg.channel, discord.TextChannel):
            # Log each message to the database
            # Unless it's in the prod-bot-media-spam channel which causes excessive logs
            if (
                self.bot.constants
                and msg.channel.id == self.bot.constants.prod_bot_media_spam
            ):
                return
            session = self.bot.helpers.get_db_session()
            try:
                # Check the configured requests channel
                settings = self.bot.guild_settings.get(msg.guild.id)
                request_channel = settings.request_channel
                #if (
                #    request_channel == msg.guild.id
                #    and not msg.content.startswith(settings.bot_prefix)
                #):

                # Check if there is a user in the database already
                db_user = (
                    session.query(models.User)
                    .filter(models.User.discord_id == msg.author.id)
                    .first()
                )
                # If no DB record for the user then create one
                if not db_user:
                    db_user = models.User(discord_id=msg.author.id)
                    session.add(db_user)
                # Check if there is a guild in the database already
                db_guild = (
                    session.query(models.Server)
                    .filter(models.Server.discord_id == msg.guild.id)
                    .first()
                )
                if not db_guild:
                    db_guild = await self.bot.helpers.db_add_new_guild(
                        session, msg.guild.id, msg.guild
                    )

                message_details = {
                    "message_id": msg.id,
                    "message_body": msg.content,
                    "channel_id": msg.channel.id,
                    "channel_name": msg.channel.name,
                }
                new_message = models.Message(
                    user=db_user, server=db_guild, **message_details
                )
                session.add(new_message)
                session.commit()
            except IntegrityError as err:
                # We don't need to log when there is a duplicate message in the database as it won't be helpful.
                # self.bot.log.debug(
                #     f"Duplicate database record: '/{msg.guild.id}/{msg.channel.id}/{msg.id}' to database. {sys.exc_info()[0].__name__}: {err}"
                # )
                session.rollback()
            except DBAPIError as err:
                self.bot.log.exception(
                    f"Generic Error logging message '/{msg.guild.id}/{msg.channel.id}/{msg.id}' to database. {sys.exc_info()[0].__name__}: {err}"
                )
                session.rollback()
            finally:
                session.close()

            # Disabling future code.. cause I'm not branching
            # Perform AntiSpam checks
            self.bot.log.debug(f"About to start AntiSpam Checks for Msg ID: {msg.id}")
            await self.bot.antispam.antispam_process_message(msg)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        try:
            if isinstance(message.channel, discord.DMChannel):
                return

            guild = message.guild
            if not guild:
                return

            # Try and get the temp logs channel
            logs = discord.utils.get(
                message.guild.text_channels, name="deleted-logs-temp"
            )

            if not logs:
                # If there is no temp logs channel, try the normal logs channel
                logs = discord.utils.get(
                    message.guild.text_channels, name="deleted-logs"
                )
                if not logs:
                    return

            # Checks if the bot can even send messages in that channel
            if not logs.permissions_for(logs.guild.me).send_messages:
                return self.bot.log.debug(
                    f"Missing Permissions to log Message Delete in Guild: {logs.guild.id} | Channel: {logs.id}"
                )

            member = message.author

            # Create the embed of info
            description = f"**Category:** {message.channel.category.name if message.channel.category else None} ({message.channel.category.id if message.channel.category else None})\n"
            description += (
                f"**Channel:** #{message.channel.name} ({message.channel.id})\n"
            )
            description += f"**Message Timestamp:** {message.created_at.replace(microsecond=0)} UTC\n"
            description += f"**Message:** ({message.id})\n\n"
            description += f"{message.clean_content[:1800]}"

            embed = discord.Embed(
                color=0x5C28C2,
                title="A Message Was Deleted",
                timestamp=datetime.utcnow(),
                description=description,
            )
            embed.set_author(name=f"{member} ({member.id})", icon_url=member.avatar_url)

            if message.attachments:
                for file in message.attachments:
                    embed.add_field(name="Attachment:", value=file.proxy_url)

            try:
                await logs.send(f"{member} ({member.id})", embed=embed)
            except discord.Forbidden:
                self.bot.log.warning(
                    f"Missing permissions to send in {logs.name} ({logs.id}) in guild {logs.guild.name} ({logs.guild.id})"
                )
        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error processing Message Delete Event. {sys.exc_info()[0].__name__}: {err}"
            )
        except Exception as err:
            self.bot.log.exception(
                f"Error processing Message Delete Event. {sys.exc_info()[ 0].__name__}: {err}"
            )

    @commands.Cog.listener()
    async def on_guild_join(self, newguild):
        session = self.bot.helpers.get_db_session()
        try:
            # Check if there is a guild in the database already
            guild = (
                session.query(models.Server)
                .filter(models.Server.discord_id == newguild.id)
                .first()
            )

            # If not, add one
            if not guild:
                guild = await self.bot.helpers.db_add_new_guild(
                    session, newguild.id, newguild
                )

            # Check if there are guild settings
            guild_settings = (
                session.query(models.ServerSetting)
                .filter(models.ServerSetting.server_id == guild.id)
                .first()
            )

            # If there is no guild settings, create them
            if not guild_settings:
                self.bot.helpers.db_add_new_guild_settings(session, guild)

            # Update local cache with new guild settings
            await self.bot.helpers.get_one_guild_settings(session, newguild.id)

            self.bot.log.info(f"Joined new guild: {newguild.name} ({newguild.id})")

            # Log in the bots support server
            guild = self.bot.get_guild(547_549_495_563_517_953)
            if guild:
                logs = discord.utils.get(guild.text_channels, name="guild-logs")
                if logs:
                    # Create the embed of info
                    embed = discord.Embed(
                        color=0x0B9CB4,
                        timestamp=datetime.utcnow(),
                        description=f"**Guild Description:** {newguild.description}",
                    )
                    embed.set_author(
                        name=f"Joined: '{newguild}' ({newguild.id})",
                        icon_url=newguild.icon_url,
                    )
                    embed.add_field(
                        name="Guild Owner",
                        value=f"{newguild.owner} ({newguild.owner.id})",
                        inline=False,
                    )
                    features = newguild.features if newguild.features else "None"
                    embed.add_field(name="Features", value=f"{features}", inline=False)
                    embed.add_field(
                        name="Total Members",
                        value=f"{newguild.member_count}",
                        inline=False,
                    )
                    embed.set_thumbnail(url=newguild.icon_url)
                    try:
                        await logs.send(embed=embed)
                    except discord.Forbidden:
                        self.bot.log.warning(
                            f"Missing permissions to send in {logs.name} ({logs.id}) in guild {logs.guild.name} ({logs.guild.id})"
                        )

        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error processing Guild Join Event. {sys.exc_info()[0].__name__}: {err}"
            )
        except DBAPIError as err:
            self.bot.log.exception(
                f"Error with Guild Join Event database calls. {sys.exc_info()[0].__name__}: {err}"
            )
            session.rollback()
        except Exception as err:
            self.bot.log.exception(
                f"Error processing Guild Join Event. {sys.exc_info()[0].__name__}: {err}"
            )
        finally:
            session.close()

    @commands.Cog.listener()
    async def on_guild_update(self, guild_before, guild_after):
        session = self.bot.helpers.get_db_session()
        try:
            # If no change in guild name, return
            if guild_before.name == guild_after.name:
                return
            # Check if there is a guild in the database already
            guild = (
                session.query(models.Server)
                .filter(models.Server.discord_id == guild_after.id)
                .first()
            )

            # If not, add one which will set the guild name, then we can return
            if not guild:
                guild = await self.bot.helpers.db_add_new_guild(
                    session, guild_after.id, guild_after
                )
                # Check if there are guild settings
                guild_settings = (
                    session.query(models.ServerSetting)
                    .filter(models.ServerSetting.server_id == guild.id)
                    .first()
                )
                # If there is no guild settings, create them
                if not guild_settings:
                    self.bot.helpers.db_add_new_guild_settings(session, guild)
                # Update local cache with new guild settings
                await self.bot.helpers.get_one_guild_settings(session, guild_after.id)
                # Now we're done processing new guild and updating the settings, return
                return
            else:
                guild.name = guild_after.name
                session.commit()
                return self.bot.log.info(
                    f"Updated guild name in DB for: {guild_after.name} ({guild_after.id})"
                )

        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error processing Guild Update Event. {sys.exc_info()[0].__name__}: {err}"
            )
        except DBAPIError as err:
            self.bot.log.exception(
                f"Error with Guild Update Event database calls. {sys.exc_info()[0].__name__}: {err}"
            )
            session.rollback()
        except Exception as err:
            self.bot.log.exception(
                f"Error processing Guild Update Event. {sys.exc_info()[0].__name__}: {err}"
            )
        finally:
            session.close()

    @commands.Cog.listener()
    async def on_guild_remove(self, oldguild):
        try:
            self.bot.log.info(f"Parted guild: {oldguild.name} ({oldguild.id})")

            # Log in the bots support server
            guild = self.bot.get_guild(547_549_495_563_517_953)
            if guild:
                logs = discord.utils.get(guild.text_channels, name="guild-logs")
                if logs:
                    # Create the embed of info
                    embed = discord.Embed(
                        color=0x06505C,
                        timestamp=datetime.utcnow(),
                        description=f"**Guild Description:** {oldguild.description}",
                    )
                    embed.set_author(
                        name=f"Parted: '{oldguild}' ({oldguild.id})",
                        icon_url=oldguild.icon_url,
                    )
                    embed.add_field(
                        name="Guild Owner",
                        value=f"{oldguild.owner} ({oldguild.owner.id})",
                        inline=False,
                    )
                    features = oldguild.features if oldguild.features else "None"
                    embed.add_field(name="Features", value=f"{features}", inline=False)
                    embed.add_field(
                        name="Total Members",
                        value=f"{oldguild.member_count}",
                        inline=False,
                    )
                    embed.set_thumbnail(url=oldguild.icon_url)
                    try:
                        await logs.send(embed=embed)
                    except discord.Forbidden:
                        self.bot.log.warning(
                            f"Missing permissions to send in {logs.name} ({logs.id}) in guild {logs.guild.name} ({logs.guild.id})"
                        )
        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error processing Guild Part Event. {sys.exc_info()[0].__name__}: {err}"
            )
        except Exception as err:
            self.bot.log.exception(
                f"Error processing Guild Part Event. {sys.exc_info()[0].__name__}: {err}"
            )

    @commands.Cog.listener()
    async def on_user_update(self, userbefore, userafter):
        session = self.bot.helpers.get_db_session()
        try:
            # If the user is this bot then skip trying to log
            if self.bot.user.id == userafter.id:
                return

            # Get the database user
            dbuser = (
                session.query(models.User)
                .filter(models.User.discord_id == userafter.id)
                .first()
            )
            # If they don't exist in the database
            if not dbuser:
                # Add them to the database
                dbuser = models.User(discord_id=userafter.id)
                session.add(dbuser)
                # Add their old alias
                old_alias = models.Alias(name=f"{userbefore}", user=dbuser)
                session.add(old_alias)

            # User can update both Alias and Avatar within one event
            embeds = []

            # User changed Avatar
            # use old user data as any other changes will show up as a second embed
            if userbefore.avatar_url != userafter.avatar_url:

                self.bot.log.debug(f"Updated avatar for {userbefore} ({userbefore.id})")

                if userbefore.is_avatar_animated():
                    avatar_ext = "gif"
                else:
                    avatar_ext = "png"

                media_channel = self.bot.get_channel(
                    self.bot.constants.prod_bot_media_spam
                )
                avatar_archived = None
                if media_channel:
                    async with aiohttp.ClientSession() as aio_session:
                        async with aio_session.get(
                            f"{userbefore.avatar_url_as(format=avatar_ext)}"
                        ) as resp:
                            archived_status = resp.status
                            if archived_status != 200:
                                avatar_archived = None
                            else:
                                data = io.BytesIO(await resp.read())
                                try:
                                    avatar_archived = await media_channel.send(
                                        file=discord.File(
                                            data,
                                            f"pfp_uid_{userbefore.id}.{avatar_ext}",
                                        )
                                    )
                                except discord.HTTPException as err:
                                    # If exception is due to following error, we're going to pass, nothing we can do, yet
                                    # A solution can be do have the dev or bot support server nitro boosted to allow
                                    # larger file uploads then move the uploads to that server
                                    # 413 REQUEST ENTITY TOO LARGE (error code: 40005): Request entity too large
                                    if err.code == 40005:
                                        avatar_archived = None
                                        pass

                # Create the embed for avatar change
                embed = discord.Embed(color=0x7289DA, timestamp=datetime.utcnow())

                description = "**Reason:** Avatar Changed\n"
                description += "Old Avatar shown on **right**\n"

                if avatar_archived is not None:
                    avatar_url = avatar_archived.attachments[0].url
                else:
                    avatar_url = userbefore.avatar_url
                    description += f"\n_Unable to acquire an archived link for old avatar._\n_Using temporary link. Please note this link will decay in the near future._\n"

                embed.set_thumbnail(url=avatar_url)
                embed.set_author(
                    name=f"{userbefore} ({userbefore.id})", icon_url=avatar_url
                )

                description += "\n\n\nNew Avatar shown **below**"
                embed.set_image(url=userafter.avatar_url)
                embed.description = description

                embeds.append(embed)

            # User name or discriminator changed
            if str(userbefore) != str(userafter):
                # Now let's add their new alias
                new_alias = models.Alias(name=f"{userafter}", user=dbuser)
                session.add(new_alias)
                session.commit()

                self.bot.log.debug(f"Updated alias for {userafter} ({userafter.id})")

                # Create the embed of info for alias change
                alias_description = f"**Reason:** Username Changed\n"
                alias_description += f"**Previous Username:** {userbefore}\n"
                alias_description += f"**New Username:** {userafter}"

                embed = discord.Embed(
                    color=0x7289DA,
                    timestamp=datetime.utcnow(),
                    description=alias_description,
                )
                embed.set_author(
                    name=f"{userafter} ({userafter.id})", icon_url=userafter.avatar_url
                )

                embed.set_thumbnail(url=userafter.avatar_url)
                embeds.append(embed)

            # No change, do nothing
            if len(embeds) == 0:
                return

            # Send to all guilds log channel
            for guild in self.bot.guilds:
                member = discord.utils.find(
                    lambda m: m.id == userafter.id, guild.members
                )
                if member:
                    logs = discord.utils.get(
                        guild.text_channels, name="name-change-logs"
                    )
                    if logs:
                        for embed in embeds:
                            try:
                                await logs.send(embed=embed)
                            except discord.Forbidden:
                                self.bot.log.warning(
                                    f"Missing permissions to send in {logs.name} ({logs.id}) in guild {logs.guild.name} ({logs.guild.id})"
                                )

        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error processing User Update Event. {sys.exc_info()[0].__name__}: {err}"
            )
        except Exception as err:
            self.bot.log.exception(
                f"Error processing User Update Event. {sys.exc_info()[0].__name__}: {err}"
            )
        except DBAPIError as err:
            self.bot.log.exception(
                f"Error with database calls for User Update event. {sys.exc_info()[0].__name__}: {err}"
            )
            session.rollback()
        finally:
            session.close()

    @commands.Cog.listener()
    async def on_member_update(self, member_before, member_after):
        try:
            # If the member is this bot then skip trying to log
            if self.bot.user.id == member_after.id:
                return
            # Check if there is a role change, then process that for the servermodrels and serveradminrels tables
            if member_before.roles != member_after.roles:
                server_admin = None
                server_mod = None
                perms_before = member_before.guild_permissions
                perms_after = member_after.guild_permissions
                # User had administrator before, but doesn't now. Need to remove the admin relationship
                if perms_before.administrator and not perms_after.administrator:
                    server_admin = False
                # User did NOT have administrator before, but does have it now. Need to add admin relationship
                elif not perms_before.administrator and perms_after.administrator:
                    server_admin = True
                else:
                    settings = self.bot.guild_settings.get(member_after.guild.id)
                    # Get their roles before and after
                    before_role_ids = [role.id for role in member_before.roles]
                    after_role_ids = [role.id for role in member_after.roles]
                    # If an admin role is set, check if that role changed
                    if settings and settings.admin_role:
                        if (
                            settings.admin_role in before_role_ids
                            and settings.admin_role not in after_role_ids
                        ):
                            server_admin = False
                        if (
                            settings.admin_role in after_role_ids
                            and settings.admin_role not in before_role_ids
                        ):
                            server_admin = True
                    # If a mod role is set, check if that role changed
                    if settings and settings.mod_role:
                        if (
                            settings.mod_role in before_role_ids
                            and settings.mod_role not in after_role_ids
                        ):
                            server_mod = False
                        if (
                            settings.mod_role in after_role_ids
                            and settings.mod_role not in before_role_ids
                        ):
                            server_mod = True

                # If there is a server admin relationship change, log it
                if server_admin is not None:
                    # Log to the database
                    session = self.bot.helpers.get_db_session()
                    try:
                        await self.bot.helpers.db_process_admin_relationship(
                            member_after, session, server_admin
                        )
                        # Commit the changes to the database
                        session.commit()
                    except IntegrityError:
                        self.bot.log.debug(
                            f"Duplicate Server Admin Relationship database record: Guild: {member_after.guild.id} | User: {member_after.id}"
                        )
                        session.rollback()
                    except DBAPIError as err:
                        self.bot.log.exception(
                            f"Database error logging Server Admin Relationship to database. {sys.exc_info()[0].__name__}: {err}"
                        )
                        session.rollback()
                    except Exception as err:
                        self.bot.log.exception(
                            f"Generic Error logging Server Admin Relationship to database. {sys.exc_info()[0].__name__}: {err}"
                        )
                        session.rollback()
                    finally:
                        session.close()
                # If there is a server mod relationship change, log it
                if server_mod is not None:
                    # Log to the database
                    session = self.bot.helpers.get_db_session()
                    try:
                        await self.bot.helpers.db_process_mod_relationship(
                            member_after, session, server_mod
                        )
                        # Commit the changes to the database
                        session.commit()
                    except IntegrityError:
                        self.bot.log.debug(
                            f"Duplicate Server Mod Relationship database record: Guild: {member_after.guild.id} | User: {member_after.id}"
                        )
                        session.rollback()
                    except DBAPIError as err:
                        self.bot.log.exception(
                            f"Database error logging Server Mod Relationship to database. {sys.exc_info()[0].__name__}: {err}"
                        )
                        session.rollback()
                    except Exception as err:
                        self.bot.log.exception(
                            f"Generic Error logging Server Mod Relationship to database. {sys.exc_info()[0].__name__}: {err}"
                        )
                        session.rollback()
                    finally:
                        session.close()

            # If there is no change to their nickname, skip
            if member_before.nick == member_after.nick:
                return

            # Get the logs channel
            logs = discord.utils.get(
                member_after.guild.text_channels, name="name-change-logs"
            )
            # If logs channel does not exist, stop processing
            if not logs:
                return

            # Create the embed of info
            description = f"**Reason:** Nickname Changed\n"
            description += f"**Previous Nickname:** {member_before.nick}\n"
            description += f"**New Nickname:** {member_after.nick}"

            embed = discord.Embed(
                color=0xDDE4E7, timestamp=datetime.utcnow(), description=description
            )
            embed.set_author(
                name=f"{member_after} ({member_after.id})",
                icon_url=member_after.avatar_url,
            )
            embed.set_thumbnail(url=member_after.avatar_url)

            try:
                await logs.send(embed=embed)
            except discord.Forbidden:
                self.bot.log.warning(
                    f"Missing permissions to send in {logs.name} ({logs.id}) in guild {logs.guild.name} ({logs.guild.id})"
                )

        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error processing User Update Event. {sys.exc_info()[0].__name__}: {err}"
            )
        except Exception as err:
            self.bot.log.exception(
                f"Error processing User Update Event. {sys.exc_info()[0].__name__}: {err}"
            )

    @commands.Cog.listener()
    async def on_member_ban(self, guild, member):
        """Watches audit log for ban events to log when it wasn't done via the bot."""

        session = self.bot.helpers.get_db_session()
        try:
            # The on member ban event only sends a guild and the member banned, but we don't know who did the banning.
            # We get the audit log, find the ban entry, and check if the person banning is same as bot, and if it is
            # then we skip logging, if not we want to log that, as it was a ban done outside the bot
            async for entry in guild.audit_logs(action=discord.AuditLogAction.ban):
                # Convert entry.user to mod variable, to avoid confusion
                mod = entry.user
                # If audit log user is not same as event member, skip
                if entry.target.id != member.id:
                    continue
                # If the user banned is by this bot then skip trying to log
                if entry.user.id == self.bot.user.id:
                    return
                self.bot.log.info(
                    f"Found native ban entry in audit log from {mod} who banned {entry.target} in {guild}"
                )

                # Since the ban was done natively, we are assuming the user was not informed
                action_text = f"{entry.reason} | Msg Delivered: No"

                await self.bot.helpers.process_ban(
                    session, member, mod, guild, entry.created_at, action_text
                )

                # Now that we found the audit log ban entry, break out so we don't process old entries
                break

        except discord.Forbidden as err:
            self.bot.log.warning(
                f"Missing permission to audit log for watching ban events."
            )
        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error processing Member Ban Event. {sys.exc_info()[0].__name__}: {err}"
            )
        except Exception as err:
            self.bot.log.exception(
                f"Error processing Member Ban Event. {sys.exc_info()[0].__name__}: {err}"
            )
        finally:
            session.close()

    @commands.Cog.listener()
    async def on_member_unban(self, guild, member):
        """Watches audit log for unban events to log when it wasn't done via the bot."""

        session = self.bot.helpers.get_db_session()
        try:
            # The on member ban event only sends a guild and the member banned, but we don't know who did the banning.
            # We get the audit log, find the ban entry, and check if the person banning is same as bot, and if it is
            # then we skip logging, if not we want to log that, as it was a ban done outside the bot
            async for entry in guild.audit_logs(action=discord.AuditLogAction.unban):
                # Convert entry.user to mod variable, to avoid confusion
                mod = entry.user
                # If audit log user is not same as event member, skip
                if entry.target.id != member.id:
                    continue
                # If the user banned is by this bot then skip trying to log
                if entry.user.id == self.bot.user.id:
                    return
                self.bot.log.info(
                    f"Found native unban entry in audit log from {mod} who unbanned {entry.target} in {guild}"
                )

                # Since the unban was done natively, we are assuming the user was not informed
                action_text = f"{entry.reason} | Msg Delivered: No"

                await self.bot.helpers.process_unban(
                    session, member, mod, guild, entry.created_at, action_text
                )

                # Now that we found the audit log ban entry, break out so we don't process old entries
                break

        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error processing Member Unban Event. {sys.exc_info()[0].__name__}: {err}"
            )
        except Exception as err:
            self.bot.log.exception(
                f"Error processing Member Unban Event. {sys.exc_info()[0].__name__}: {err}"
            )
        finally:
            session.close()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, raw_reaction_action_event):
        try:
            self.bot.log.debug(
                f"New Raw Reaction Event (Add), mID: {raw_reaction_action_event.message_id}"
            )
            # If the member is this bot then skip trying to process
            if raw_reaction_action_event.user_id == self.bot.user.id:
                return

            # Set variables
            guild_id = raw_reaction_action_event.guild_id
            message_id = raw_reaction_action_event.message_id
            channel_id = raw_reaction_action_event.channel_id
            user_id = raw_reaction_action_event.user_id
            emoji = raw_reaction_action_event.emoji

            # Process/Check if need to for Role Assignment
            await self.bot.assignment.process_role(
                guild_id, channel_id, message_id, user_id, emoji
            )

            # Get channel ID's the command request command goes to
            settings = self.bot.guild_settings.get(guild_id)
            upvote_emoji = settings.upvote_emoji or self.bot.constants.reactions["upvote"]
            downvote_emoji = settings.downvote_emoji or self.bot.constants.reactions["downvote"]
            question_emoji = settings.question_emoji or self.bot.constants.reactions["question"]

            downvotes_allowed = settings.allow_downvotes
            questions_allowed = settings.allow_questions
            
            try:
                request_channel_id = settings.request_channel
            except Exception as err:
                # If no request_channel or settings returned from the DB settings then return
                return
            # Check if the reaction is on a request, and if so adjust the voting:
            if channel_id == request_channel_id:
                self.bot.log.debug(
                    f"Reaction is in the request channel. Request mID: {message_id}"
                )
                upvoted = False
                downvoted = False
                questioned = False

                # Get the reactions
                upvote = self.bot.get_emoji(upvote_emoji)
                downvote = self.bot.get_emoji(downvote_emoji)
                question = self.bot.get_emoji(question_emoji)

                if emoji.id == upvote.id:
                    upvoted = True
                elif (
                  emoji.id == downvote.id
                  and downvotes_allowed
                ):
                    downvoted = True
                elif (
                  emoji.id == question.id
                  and questions_allowed
                ):
                    questioned = True

                if upvoted or downvoted or questioned:
                    self.bot.log.debug(
                        f"Request was voted on: Request mID: {message_id}"
                    )
                    # Get the database record
                    session = self.bot.helpers.get_db_session()
                    try:
                        request_result = (
                            session.query(models.Requests).filter(
                                models.Requests.message_id == message_id
                            )
                        ).first()
                        if request_result:
                            self.bot.log.debug(
                                f"Found request in the database. Request mID: {message_id}"
                            )
                            if upvoted:
                                request_result.upvotes = (
                                    models.Requests.upvotes + 1
                                )
                                self.bot.log.debug(
                                    f"Request Event: Upvote + 1. Request mID: {message_id}"
                                )
                            elif downvoted:
                                request_result.downvotes = (
                                    models.Requests.downvotes + 1
                                )
                                self.bot.log.debug(
                                    f"Request Event: Downvote + 1. Request mID: {message_id}"
                                )
                            elif questioned:
                                request_result.questions = (
                                    models.Requests.questions + 1
                                )
                            # Commit change to database
                            session.commit()
                            self.bot.log.debug(
                                f"Committed change to database. Request mID: {message_id}"
                            )
                        else:
                            self.bot.log.debug(
                                f"Request NOT in the database. Request mID: {message_id}"
                            )
                    except DBAPIError as err:
                        self.bot.log.exception(
                            f"Error processing database query for adjusting Request votes. {sys.exc_info()[0].__name__}: {err}"
                        )
                        session.rollback()
                    except Exception as err:
                        self.bot.log.exception(
                            f"Unknown Error logging to database for adjusting Request votes. {sys.exc_info()[0].__name__}: {err}"
                        )
                    finally:
                        session.close()

        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error processing Raw Reaction Add Event. {sys.exc_info()[0].__name__}: {err}"
            )
        except Exception as err:
            self.bot.log.exception(
                f"Error processing Raw Reaction Add Event. {sys.exc_info()[0].__name__}: {err}"
            )

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, raw_reaction_action_event):
        try:
            self.bot.log.debug(
                f"New Raw Reaction Event (Remove), mID: {raw_reaction_action_event.message_id}"
            )
            # If the member is this bot then skip trying to process
            if raw_reaction_action_event.user_id == self.bot.user.id:
                return

            # Set variables
            guild_id = raw_reaction_action_event.guild_id
            message_id = raw_reaction_action_event.message_id
            channel_id = raw_reaction_action_event.channel_id
            user_id = raw_reaction_action_event.user_id
            emoji = raw_reaction_action_event.emoji

            # Get channel ID's the command request command goes to
            settings = self.bot.guild_settings.get(guild_id)
            upvote_emoji = settings.upvote_emoji or self.bot.constants.reactions["upvote"]
            downvote_emoji = settings.downvote_emoji or self.bot.constants.reactions["downvote"]
            question_emoji = settings.question_emoji or self.bot.constants.reactions["question"]

            try:
                request_channel_id = settings.request_channel
            except Exception as err:
                # If no request_channel or settings returned from the DB settings then return
                return
            # Check if the reaction is on a request, and if so adjust the voting:
            if channel_id == request_channel_id:
                self.bot.log.debug(
                    f"Reaction is in the request channel. Request mID: {message_id}"
                )
                upvoted = False
                downvoted = False
                questioned = False

                # Get the reactions
                upvote = self.bot.get_emoji(upvote_emoji)
                downvote = self.bot.get_emoji(downvote_emoji)
                question = self.bot.get_emoji(question_emoji)

                if emoji.id == upvote.id:
                    upvoted = True
                elif emoji.id == downvote.id:
                    downvoted = True
                elif emoji.id == question.id:
                    questioned = True

                if upvoted or downvoted or questioned:
                    self.bot.log.debug(
                        f"Request was voted on: Request mID: {message_id}"
                    )
                    # Get the database record
                    session = self.bot.helpers.get_db_session()
                    try:
                        request_result = (
                            session.query(models.Requests).filter(
                                models.Requests.message_id == message_id
                            )
                        ).first()
                        if request_result:
                            self.bot.log.debug(
                                f"Found request in the database. Request mID: {message_id}"
                            )
                            if upvoted:
                                request_result.upvotes = (
                                    models.Requests.upvotes - 1
                                )
                                self.bot.log.debug(
                                    f"Request Event: Upvote - 1. Request mID: {message_id}"
                                )
                            elif downvoted:
                                request_result.downvotes = (
                                    models.Requests.downvotes - 1
                                )
                                self.bot.log.debug(
                                    f"Request Event: Downvote - 1. Request mID: {message_id}"
                                )
                            elif questioned:
                                request_result.questions = (
                                    models.Requests.questions - 1
                                )
                            # Commit change to database
                            session.commit()
                            self.bot.log.debug(
                                f"Committed change to database. Request mID: {message_id}"
                            )
                        else:
                            self.bot.log.debug(
                                f"Request NOT in the database. Request mID: {message_id}"
                            )
                    except DBAPIError as err:
                        self.bot.log.exception(
                            f"Error processing database query for adjusting request votes. {sys.exc_info()[0].__name__}: {err}"
                        )
                        session.rollback()
                    except Exception as err:
                        self.bot.log.exception(
                            f"Unknown Error logging to database for adjusting request votes. {sys.exc_info()[0].__name__}: {err}"
                        )
                    finally:
                        session.close()

        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error processing Raw Reaction Remove Event. {sys.exc_info()[0].__name__}: {err}"
            )
        except Exception as err:
            self.bot.log.exception(
                f"Error processing Raw Reaction Remove Event. {sys.exc_info()[0].__name__}: {err}"
            )

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, member):
        try:
            # If the member is this bot then skip trying to log
            if self.bot.user.id == member.id:
                return

            guild = reaction.message.guild
            if not guild:
                return

            # Get the logs channel
            logs = discord.utils.get(guild.text_channels, name="reaction-logs")
            if not logs:
                return

            # Create the embed of info
            description = f"**Reason:** A reaction was added\n"
            description += f"**Channel:** #{reaction.message.channel.name} ({reaction.message.channel.id})\n"
            description += f"**Message:** ({reaction.message.id})\n"
            # If the emoji is a unicode emoji then it is a string
            if type(reaction.emoji) is str:
                description += f"**Emoji:** {reaction.emoji}\n"
            else:
                description += (
                    f"**Emoji:** {reaction.emoji.name} ({reaction.emoji.id})\n"
                )
            # If the bot isn't in the server the emoji is from, it gets a PartialEmoji type and we lack guild info
            if isinstance(reaction.emoji, discord.Emoji):
                description += f"**Source Guild:** {reaction.emoji.guild.name} ({reaction.emoji.guild.id})\n"
            description += f"**Message Link:** https://discordapp.com/channels/{guild.id}/{reaction.message.channel.id}/{reaction.message.id}"

            embed = discord.Embed(
                color=0x64997D, timestamp=datetime.utcnow(), description=description
            )
            embed.set_author(name=f"{member} ({member.id})", icon_url=member.avatar_url)
            # If the emoji is a unicode emoji then it is a string
            if type(reaction.emoji) is not str:
                embed.set_thumbnail(url=reaction.emoji.url)

            try:
                await logs.send(embed=embed)
            except discord.Forbidden:
                self.bot.log.warning(
                    f"Missing permissions to send in {logs.name} ({logs.id}) in guild {guild.name} ({guild.id})"
                )

        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error processing Reaction Add Event. {sys.exc_info()[0].__name__}: {err}"
            )
        except Exception as err:
            self.bot.log.exception(
                f"Error processing Reaction Add Event. {sys.exc_info()[0].__name__}: {err}"
            )

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction, member):
        try:
            # If the member is this bot then skip trying to log
            if self.bot.user.id == member.id:
                return

            guild = reaction.message.guild
            if not guild:
                return

            guild = reaction.message.guild

            # Get the logs channel
            logs = discord.utils.get(guild.text_channels, name="reaction-logs")
            if not logs:
                return

            # Create the embed of info
            description = f"**Reason:** A reaction was removed\n"
            description += f"**Channel:** #{reaction.message.channel.name} ({reaction.message.channel.id})\n"
            description += f"**Message:** ({reaction.message.id})\n"
            # If the emoji is a unicode emoji then it is a string
            if type(reaction.emoji) is str:
                description += f"**Emoji:** {reaction.emoji}\n"
            else:
                description += (
                    f"**Emoji:** {reaction.emoji.name} ({reaction.emoji.id})\n"
                )
            # If the bot isn't in the server the emoji is from, it gets a PartialEmoji type and we lack guild info
            if isinstance(reaction.emoji, discord.Emoji):
                description += f"**Source Guild:** {reaction.emoji.guild.name} ({reaction.emoji.guild.id})\n"
            description += f"**Message Link:** https://discordapp.com/channels/{guild.id}/{reaction.message.channel.id}/{reaction.message.id}"

            embed = discord.Embed(
                color=0xED8F45, timestamp=datetime.utcnow(), description=description
            )
            embed.set_author(name=f"{member} ({member.id})", icon_url=member.avatar_url)
            # If the emoji is a unicode emoji then it is a string
            if type(reaction.emoji) is not str:
                embed.set_thumbnail(url=reaction.emoji.url)

            try:
                await logs.send(embed=embed)
            except discord.Forbidden:
                self.bot.log.warning(
                    f"Missing permissions to send in {logs.name} ({logs.id}) in guild {guild.name} ({guild.id})"
                )

        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error processing Reaction Remove Event. {sys.exc_info()[0].__name__}: {err}"
            )
        except Exception as err:
            self.bot.log.exception(
                f"Error processing Reaction Remove Event. {sys.exc_info()[0].__name__}: {err}"
            )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member, voice_state_before, voice_state_after
    ):
        try:
            # If the member is this bot then skip trying to log
            if self.bot.user.id == member.id:
                return

            # Get the guild of the before event
            before_guild = (
                voice_state_before.channel.guild if voice_state_before.channel else None
            )
            # Get the guild of the after event
            after_guild = (
                voice_state_after.channel.guild if voice_state_after.channel else None
            )

            # Get the logs channel for before guild
            if before_guild:
                before_logs = discord.utils.get(
                    before_guild.text_channels, name="voice-logs"
                )
            # Get the logs channel for after guild
            if after_guild:
                after_logs = discord.utils.get(
                    after_guild.text_channels, name="voice-logs"
                )

            # Set the event types
            reason = None
            # If before_guild is none, but after_guild exists, they joined a channel
            old_channel_members_ids = None
            new_channel_members_ids = None
            if before_guild is None and after_guild:
                # New channel
                (
                    new_channel_members,
                    new_channel_members_ids,
                ) = await self.bot.helpers.get_voice_channel_members(
                    member, voice_state_after.channel.members, include_self=False
                )

                reason = "Joined Voice Channel"
                event_details = f"**New Channel:** #{voice_state_after.channel.name} ({voice_state_after.channel.id})\n"
                event_details += f"**New Channel Users:** {new_channel_members}\n"
            # If after_guild is none, but before_guild exists, they left a channel
            elif after_guild is None and before_guild:
                # Old channel
                (
                    old_channel_members,
                    old_channel_members_ids,
                ) = await self.bot.helpers.get_voice_channel_members(
                    member, voice_state_before.channel.members, include_self=True
                )

                reason = "Left Voice Channel"
                event_details = f"**Old Channel:** #{voice_state_before.channel.name} ({voice_state_before.channel.id})\n"
                event_details += f"**Old Channel Users:** {old_channel_members}\n"
            # If before_guild and after_guild exists, they moved voice channels
            elif (before_guild and after_guild) and (
                voice_state_before.channel.id != voice_state_after.channel.id
            ):
                # Old channel
                (
                    old_channel_members,
                    old_channel_members_ids,
                ) = await self.bot.helpers.get_voice_channel_members(
                    member, voice_state_before.channel.members, include_self=True
                )
                # New channel
                (
                    new_channel_members,
                    new_channel_members_ids,
                ) = await self.bot.helpers.get_voice_channel_members(
                    member, voice_state_after.channel.members, include_self=False
                )

                reason = "Moved Voice Channel"
                event_details = f"**Old Channel:** #{voice_state_before.channel.name} ({voice_state_before.channel.id})\n"
                event_details += f"**Old Channel Users:** {old_channel_members}\n"
                event_details += f"**New Channel:** #{voice_state_after.channel.name} ({voice_state_after.channel.id})\n"
                event_details += f"**New Channel Users:** {new_channel_members}\n"
            else:
                reason = "Unknown"
                return

            # Log to the database
            session = self.bot.helpers.get_db_session()
            try:
                # Get the DB profile for the guild
                db_guild = await self.bot.helpers.db_get_guild(session, member.guild.id)
                # Get the DB profile for the user
                db_user = await self.bot.helpers.db_get_user(session, member.id)
                db_voice = models.VoiceLog(
                    user=db_user,
                    server=db_guild,
                    event_type=reason,
                    # Old Channel
                    vc_old_name=voice_state_before.channel.name
                    if before_guild
                    else None,
                    vc_old_id=voice_state_before.channel.id if before_guild else None,
                    vc_old_users_ids=old_channel_members_ids if before_guild else None,
                    # New channel
                    vc_new_name=voice_state_after.channel.name if after_guild else None,
                    vc_new_id=voice_state_after.channel.id if after_guild else None,
                    vc_new_users_ids=new_channel_members_ids if after_guild else None,
                )
                session.add(db_voice)
                session.commit()
                self.bot.log.debug(
                    f"Voice Log to database: Guild: {member.guild.id}, User: {member.id}"
                )
            except DBAPIError as err:
                self.bot.log.exception(
                    f"Database error logging voice state update to database. {sys.exc_info()[0].__name__}: {err}"
                )
                session.rollback()
            except Exception as err:
                self.bot.log.exception(
                    f"Generic Error logging Voice State Update Event to database. {sys.exc_info()[0].__name__}: {err}"
                )
            finally:
                session.close()

            # Create the embed of info
            description = f"**Reason:** {reason}\n"
            description += event_details

            embed = discord.Embed(
                color=0xFFC0CB, timestamp=datetime.utcnow(), description=description
            )
            embed.set_author(name=f"{member} ({member.id})", icon_url=member.avatar_url)

            try:
                if before_guild and before_logs:
                    return await before_logs.send(embed=embed)

                elif after_guild and after_logs:
                    return await after_logs.send(embed=embed)
            except discord.Forbidden:
                self.bot.log.warning(f"Missing permissions to send in logs channel")

        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error processing Voice State Update Event. {sys.exc_info()[0].__name__}: {err}"
            )
        except Exception as err:
            self.bot.log.exception(
                f"Error processing Voice State Update Event. {sys.exc_info()[0].__name__}: {err}"
            )


def setup(bot):
    bot.add_cog(Events(bot))
