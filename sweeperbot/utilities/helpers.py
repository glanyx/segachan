import asyncio
import datetime
import re
import sys

import discord
import redis
from discord.ext import commands
from sentry_sdk import configure_scope
from sqlalchemy import desc
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import aliased
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import literal_column

from sweeperbot.cogs.utils.timer import Timer
from sweeperbot.db import models


class Helpers:
    def __init__(self, bot):
        self.bot = bot
        redis_host = self.bot.botconfig.get("Redis", "HOST")
        redis_password = self.bot.botconfig.get("Redis", "PASSWORD")
        redis_database = self.bot.botconfig.get("Redis", "DATABASE")
        self.redis = redis.Redis(
            host=redis_host,
            port=6379,
            db=redis_database,
            decode_responses=True,
            password=redis_password,
        )

    async def get_member_or_user(self, input_str: str, guild: discord.Guild = None):
        # Let's clean the input first (could be an ID or a mention)
        if type(input_str) != int:
            user_id = self.clean_mention(input_str)
        else:
            user_id = input_str
        # Let's try to get a member on the server
        if guild:
            if user_id:
                # Get user from internal cache
                member = guild.get_member(user_id)
                if member:
                    return member
                else:
                    # Fetch with an API call
                    try:
                        member = await guild.fetch_member(user_id)
                        if member:
                            return member
                    except (discord.NotFound, discord.HTTPException):
                        # No user found, pass
                        pass
            else:
                # Try and search for them by name
                member = discord.utils.find(
                    lambda mbr: str(mbr).lower() == input_str.lower(), guild.members
                )
                if member:
                    return member

        # Try to get a user from local cache first
        if user_id:
            user = self.bot.get_user(user_id)
            if user:
                return user
            # If no user, fetch with an API call
            else:
                try:
                    user = await self.bot.fetch_user(user_id)
                    if user:
                        return user
                except (discord.NotFound, discord.HTTPException):
                    # No user found, pass
                    pass
        else:
            user = discord.utils.find(
                lambda usr: str(usr).lower() == input_str, self.bot.users
            )
            if user:
                return user

        # If we make it this far, return None
        return None

    def clean_mention(self, mention: str):
        """Takes a mention, and tries to return the underlying Discord ID"""

        mention_temp = mention
        # If the 5th character from the right is a pound symbol, then it's a name#discrim not a mention or Discord ID
        if len(mention) > 5 and mention[-5] == "#":
            return None
        # Clean the mention to be just an ID
        for char in ["<", "#", "&", "@", "!", ">", "(", ")"]:
            mention_temp = mention_temp.replace(char, "")

        try:
            return int(mention_temp)
        except ValueError:
            return None

    def relative_time(self, start_time, end_time, brief=False):
        if start_time is None or end_time is None:
            return "Unknown"
        delta = start_time - end_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)

        if not brief:
            if days:
                fmt = "{d:,} days, {h} hours, {m} minutes, and {s} seconds"
            else:
                fmt = "{h} hours, {m} minutes, and {s} seconds"
        else:
            fmt = "{m}m {s}s"
            if days or hours:
                fmt = "{h:,}h " + fmt
                if days:
                    fmt = "{d:,}d " + fmt

        return fmt.format(d=days, h=hours, m=minutes, s=seconds)

    async def process_ban(
        self, session, member, mod, guild, action_timestamp, action_text
    ):
        db_logged = False
        chan_logged = False
        try:
            # Try and log to the database
            new_ban = None
            try:
                # Get mod's DB profile
                db_mod = await self.bot.helpers.db_get_user(session, mod.id)
                # Get the DB profile for the guild
                db_guild = await self.bot.helpers.db_get_guild(session, guild.id)
                # Get the DB profile for the user
                db_user = await self.bot.helpers.db_get_user(session, member.id)

                # Log the action to the database
                logged_action = models.Action(mod=db_mod, server=db_guild)
                new_ban = models.Ban(
                    text=action_text,
                    user=db_user,
                    server=db_guild,
                    action=logged_action,
                )
                session.add(new_ban)
                session.commit()
                db_logged = True
            except DBAPIError as err:
                self.bot.log.exception(
                    f"Error logging ban to database for: ({member}). {sys.exc_info()[0].__name__}: {err}"
                )
                session.rollback()
                db_logged = False

            # Try and log to the logs channel
            try:
                # Create the embed of info
                description = (
                    f"**Member:** {member} ({member.id})\n"
                    f"**Moderator:** {mod} ({mod.id})\n"
                    f"**Reason:** {action_text[:1900]}"
                )

                embed = discord.Embed(
                    color=0xE50000,
                    timestamp=action_timestamp,
                    title=f"A user was banned | *#{new_ban.id if new_ban else 'n/a'}*",
                    description=description,
                )
                embed.set_author(
                    name=f"{member} ({member.id})", icon_url=member.avatar_url
                )
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
                        chan_logged = True
            except Exception as err:
                self.bot.log.exception(
                    f"Error logging ban in channel for user: '{member.id}' in Guild: '{guild.id}'. {sys.exc_info()[0].__name__}: {err}"
                )
        except Exception as err:
            self.bot.log.exception(
                f"Error processing ban for user: '{member.id}' in Guild: '{guild.id}'. {sys.exc_info()[0].__name__}: {err}"
            )
            raise
        finally:
            return db_logged, chan_logged

    async def process_unban(
        self, session, member, mod, guild, action_timestamp, action_text="None"
    ):
        db_logged = False
        chan_logged = False
        try:
            # Try and log to the database
            new_note = None
            try:
                # Get mod's DB profile
                db_mod = await self.bot.helpers.db_get_user(session, mod.id)
                # Get the DB profile for the guild
                db_guild = await self.bot.helpers.db_get_guild(session, guild.id)
                # Get the DB profile for the user
                db_user = await self.bot.helpers.db_get_user(session, member.id)

                logged_action = models.Action(mod=db_mod, server=db_guild)
                new_note = models.Note(
                    text=f"(Unban) {action_text}",
                    user=db_user,
                    server=db_guild,
                    action=logged_action,
                )
                session.add(new_note)
                session.commit()
                db_logged = True
            except DBAPIError as err:
                self.bot.log.exception(
                    f"Error logging unban to database for: ({member}). {sys.exc_info()[0].__name__}: {err}"
                )
                session.rollback()
                db_logged = False

            # Create the embed of info
            description = (
                f"**Member:** {member} ({member.id})\n"
                f"**Moderator:** {mod} ({mod.id})\n"
                f"**Reason:** {action_text[:1900]}"
            )

            embed = discord.Embed(
                color=0xBDBDBD,
                timestamp=action_timestamp,
                title=f"A users ban was removed | *#{new_note.id if new_note else 'n/a'}*",
                description=description,
            )
            embed.set_author(name=f"{member} ({member.id})", icon_url=member.avatar_url)
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
                    chan_logged = True

        except Exception as err:
            self.bot.log.exception(
                f"Error processing ban for user: '{member.id}' in Guild: '{guild.id}'. {sys.exc_info()[0].__name__}: {err}"
            )
            raise
        finally:
            return db_logged, chan_logged

    def normal_name(self, input_text):
        return re.sub(self.bot.constants.normalize_regex, "", input_text.lower())

    async def get_voice_channel_members(self, member, members_list, include_self):
        # Create a mention list for the embed
        tmp_members_mention = [tmp_user.mention for tmp_user in members_list]
        if include_self:
            tmp_members_mention.append(member.mention)
        channel_members = ", ".join(tmp_members_mention)
        # Create a id list for the database logging
        channel_members_ids = [tmp_user.id for tmp_user in members_list]
        if include_self:
            channel_members_ids.append(member.id)
        # Return the data
        return channel_members, channel_members_ids

    async def get_guild_invite(self, guild):
        invite = None
        try:
            all_invites = await guild.invites()
            # If the server doesn't have any invites, let's try and create one
            if all_invites is None:
                # Let's try and create one.. by iterating through every channel until we find the perms
                for channel in guild.text_channels:
                    try:
                        # Create invite to last 60 seconds, we don't need it long.
                        tmp_invite = await channel.create_invite(
                            max_age=60, reason="Getting Guild Stats"
                        )
                        # Now we need to fetch it so we get counts
                        invite = await self.bot.fetch_invite(
                            tmp_invite.code, with_counts=True
                        )
                        # Once we find a good candidate then break out
                        break
                    except Exception:
                        pass

            else:
                # If the server has an invite, let's use that instead
                for tmp_invite in all_invites:
                    invite = await self.bot.fetch_invite(
                        tmp_invite.code, with_counts=True
                    )
                    break
        except discord.errors.Forbidden:
            pass
        except asyncio.TimeoutError as err:
            self.bot.log.warning(
                f"TimeoutError getting Guild Invite. {sys.exc_info()[0].__name__}: {err}"
            )
        except Exception as err:
            self.bot.log.exception(
                f"Generic Error getting Guild Invite. {sys.exc_info()[0].__name__}: {err}"
            )
        finally:
            return invite

    # Database Functions
    def get_db_session(self, db_config="Database"):
        try:
            return self.bot.database.get_session(db_config)
        except Exception as err:
            self.bot.log.exception(f"Error getting session. Error: {err}")
            return None

    def get_all_guild_settings(self):
        session = self.get_db_session()
        try:
            self.bot.log.info(f"Getting all guild settings")
            # Get all guild settings where the bot is in that guild
            guild_settings = session.query(models.ServerSetting).filter().all()

            all_settings = {}
            # TO DO - This could probably be combined with above query using a join
            if guild_settings:
                for guild in guild_settings:
                    guild_id = (
                        session.query(models.Server)
                        .filter(models.Server.id == guild.server_id)
                        .first()
                    ).discord_id

                    all_settings[guild_id] = guild

            self.bot.guild_settings = all_settings
            self.bot.log.info(f"Done getting all guild settings")
        except Exception as err:
            self.bot.log.exception(
                f"Error getting all guild settings. {sys.exc_info()[0].__name__}: {err}"
            )
            session.rollback()
        finally:
            session.close()

    def db_get_cooldown_settings(self):
        session = self.get_db_session()
        try:
            self.bot.log.info(f"Getting all cooldown settings")
            # Get all guild settings where the bot is in that guild
            cooldown_settings = session.query(models.Cooldowns).filter().all()

            all_settings = {}
            for setting in cooldown_settings:
                all_settings[setting.name] = setting

            self.bot.cooldown_settings = all_settings
            self.bot.log.info(f"Done getting all cooldown settings")
        except Exception as err:
            self.bot.log.exception(
                f"Error getting all cooldown settings. {sys.exc_info()[0].__name__}: {err}"
            )
            session.rollback()
        finally:
            session.close()

    async def get_one_guild_settings(self, session, guild_id):
        try:
            # Get guild settings
            guild_settings = (
                session.query(models.ServerSetting)
                .join(models.Server)
                .filter(models.Server.discord_id == guild_id)
                .first()
            )
            if not guild_settings:
                # Check if there is a guild in the database already
                guild = (
                    session.query(models.Server)
                    .filter(models.Server.discord_id == guild_id)
                    .first()
                )
                # If not, add one
                if not guild:
                    guild = await self.db_add_new_guild(session, guild_id)
                # Now that we have a guild, let's finally create the settings
                guild_settings = await self.db_add_new_guild_settings(session, guild)

            return guild_settings
        except Exception as err:
            self.bot.log.exception(
                f"Error getting guild setting for {guild_id}. {sys.exc_info()[0].__name__}: {err}"
            )
            session.rollback()

    async def db_add_new_guild(self, session, guild_id, guild=None):
        try:
            if guild:
                new_guild = models.Server(discord_id=guild.id, name=guild.name)
            else:
                new_guild = models.Server(discord_id=guild_id)
            session.add(new_guild)
            session.commit()
            self.bot.log.debug(f"Added new guild to DB: {guild_id}")
            return new_guild
        except Exception as err:
            self.bot.log.exception(
                f"Error adding new guild '{guild_id}' to database. {sys.exc_info()[0].__name__}: {err}"
            )
            session.rollback()

    async def db_add_new_guild_settings(self, session, guild):
        try:
            new_settings = models.ServerSetting(server=guild)
            session.add(new_settings)
            session.commit()
            self.bot.log.debug(
                f"Added new guild setting to DB for guild: {guild.discord_id}"
            )
            return new_settings
        except Exception as err:
            self.bot.log.exception(
                f"Error adding new guild settings '{guild.discord_id}' to database. {sys.exc_info()[0].__name__}: {err}"
            )
            session.rollback()
            raise

    async def db_get_user(self, session, discord_id):
        try:
            # Try and get record from database
            db_user = (
                session.query(models.User)
                .filter(models.User.discord_id == discord_id)
                .first()
            )
            # If no DB record for the user then create one
            if not db_user:
                db_user = models.User(discord_id=discord_id)
                session.add(db_user)
                session.commit()
                self.bot.log.debug(f"Added new user to DB: {discord_id}")
            return db_user
        except Exception as err:
            self.bot.log.exception(
                f"Error getting / adding user to database: '{discord_id}'. {sys.exc_info()[0].__name__}: {err}"
            )

    async def db_get_guild(self, session, discord_id):
        try:
            # Try and get record from database
            db_guild = (
                session.query(models.Server)
                .filter(models.Server.discord_id == discord_id)
                .first()
            )
            # If no DB record for the guild, create one
            if not db_guild:
                self.bot.log.debug(
                    f"No guild in DB found for {discord_id} - creating a new record"
                )
                db_guild = await self.bot.helpers.db_add_new_guild(session, discord_id)
            return db_guild
        except Exception as err:
            self.bot.log.exception(
                f"Error getting / adding guild to database: '{discord_id}'. {sys.exc_info()[0].__name__}: {err}"
            )

    async def get_action_history(self, session, user, guild):
        try:
            # Creates an alias to the User table specifically to be used for the user.
            # Otherwise using models.User.discord_id == user.id will match against the Mod
            # due to prior join to the User table
            user_alias = aliased(models.User)

            # Note Query
            note_query = (
                session.query(
                    models.Note.id,
                    models.Note.created.label("created"),
                    models.Note.text,
                    models.User,
                    literal_column("'Note'").label("type"),
                    models.Note.created.label("expires"),
                )
                # Links the Note and Action table (used for next 2 joins)
                .join(models.Action, models.Action.id == models.Note.action_id)
                # Links the User and Action table to get the Mod
                .join(models.User, models.User.id == models.Action.mod_id)
                # Links the Server and Note table to get the Guild
                .join(models.Server, models.Server.id == models.Note.server_id)
                # Links the User and Note table to get the User
                .join(user_alias, user_alias.id == models.Note.user_id)
                # Filters on the user alias where the users Discord ID matches
                # And where the guilds Discord ID matches
                .filter(
                    user_alias.discord_id == user.id,
                    models.Server.discord_id == guild.id,
                )
            )
            # Mute Query
            mute_query = (
                session.query(
                    models.Mute.id,
                    models.Mute.created.label("created"),
                    models.Mute.text,
                    models.User,
                    literal_column("'Mute'").label("type"),
                    models.Mute.expires,
                )
                # Links the Mute and Action table (used for next 2 joins)
                .join(models.Action, models.Action.id == models.Mute.action_id)
                # Links the User and Action table to get the Mod
                .join(models.User, models.User.id == models.Action.mod_id)
                # Links the Server and Mute table to get the Guild
                .join(models.Server, models.Server.id == models.Mute.server_id)
                # Links the User and Mute table to get the User
                .join(user_alias, user_alias.id == models.Mute.user_id)
                # Filters on the user alias where the users Discord ID matches
                # And where the guilds Discord ID matches
                .filter(
                    user_alias.discord_id == user.id,
                    models.Server.discord_id == guild.id,
                )
            )
            # Warn Query
            warn_query = (
                session.query(
                    models.Warn.id,
                    models.Warn.created.label("created"),
                    models.Warn.text,
                    models.User,
                    literal_column("'Warn'").label("type"),
                    models.Warn.created.label("expires"),
                )
                # Links the Warn and Action table (used for next 2 joins)
                .join(models.Action, models.Action.id == models.Warn.action_id)
                # Links the User and Action table to get the Mod
                .join(models.User, models.User.id == models.Action.mod_id)
                # Links the Server and Warn table to get the Guild
                .join(models.Server, models.Server.id == models.Warn.server_id)
                # Links the User and Warn table to get the User
                .join(user_alias, user_alias.id == models.Warn.user_id)
                # Filters on the user alias where the users Discord ID matches
                # And where the guilds Discord ID matches
                .filter(
                    user_alias.discord_id == user.id,
                    models.Server.discord_id == guild.id,
                )
            )
            # Warn Query
            kick_query = (
                session.query(
                    models.Kick.id,
                    models.Kick.created.label("created"),
                    models.Kick.text,
                    models.User,
                    literal_column("'Kick'").label("type"),
                    models.Kick.created.label("expires"),
                )
                # Links the Kick and Action table (used for next 2 joins)
                .join(models.Action, models.Action.id == models.Kick.action_id)
                # Links the User and Action table to get the Mod
                .join(models.User, models.User.id == models.Action.mod_id)
                # Links the Server and Kick table to get the Guild
                .join(models.Server, models.Server.id == models.Kick.server_id)
                # Links the User and Kick table to get the User
                .join(user_alias, user_alias.id == models.Kick.user_id)
                # Filters on the user alias where the users Discord ID matches
                # And where the guilds Discord ID matches
                .filter(
                    user_alias.discord_id == user.id,
                    models.Server.discord_id == guild.id,
                )
            )
            # Ban Query
            ban_query = (
                session.query(
                    models.Ban.id,
                    models.Ban.created.label("created"),
                    models.Ban.text,
                    models.User,
                    literal_column("'Ban'").label("type"),
                    models.Ban.created.label("expires"),
                )
                # Links the Ban and Action table (used for next 2 joins)
                .join(models.Action, models.Action.id == models.Ban.action_id)
                # Links the User and Action table to get the Mod
                .join(models.User, models.User.id == models.Action.mod_id)
                # Links the Server and Ban table to get the Guild
                .join(models.Server, models.Server.id == models.Ban.server_id)
                # Links the User and Ban table to get the User
                .join(user_alias, user_alias.id == models.Ban.user_id)
                # Filters on the user alias where the users Discord ID matches
                # And where the guilds Discord ID matches
                .filter(
                    user_alias.discord_id == user.id,
                    models.Server.discord_id == guild.id,
                )
            )
            # Get the results from the database
            results = note_query.union(
                warn_query, kick_query, mute_query, ban_query
            ).order_by(desc("created"))
            # Format the results
            note_count = 0
            warn_count = 0
            mute_count = 0
            kick_count = 0
            ban_count = 0
            total_count = 0
            embed_result_entries = []
            for result in results:
                total_count += 1
                # Set variables to make readability easier
                action_dbid = result[0]
                action_date = result[1]
                action_date_friendly = result[1].strftime("%b %d, %Y %I:%M %p") + " UTC"
                action_text = result[2]
                action_mod = result[3]
                action_type = result[4]
                action_expires = result[5]
                action_length_friendly = ""
                # Count how many of each action
                if action_type == "Note":
                    note_count += 1
                elif action_type == "Warn":
                    warn_count += 1
                elif action_type == "Kick":
                    kick_count += 1
                elif action_type == "Mute":
                    mute_count += 1
                    action_length = self.bot.helpers.relative_time(
                        start_time=action_expires, end_time=action_date, brief=True
                    )
                    action_length_friendly = f" [{action_length}]"
                elif action_type == "Ban":
                    ban_count += 1

                # Truncate the embed action text to avoid long messages
                if action_text and len(action_text) > 750:
                    action_text = f"{action_text[:750]}..."
                # Format the embed
                data_title = f"{action_type}{action_length_friendly} - {action_date_friendly} | *#{action_dbid}*"
                data_value = f"{action_text} - <@{action_mod.discord_id}>"

                embed_result_entries.append([data_title, data_value])
            # Handle if there were no records returned so the users know there's nothing vs a bot error
            if total_count is 0:
                embed_result_entries.append(["History Data:", "None"])
            # Set the footer
            footer_text = f"Note: {note_count}, Warn: {warn_count}, Mute: {mute_count}, Kick: {kick_count}, Ban: {ban_count}"
            # Return the results
            return embed_result_entries, footer_text
        except Exception as err:
            self.bot.log.exception(
                f"Error getting history from database for User: '{user.id}' in Guild: '{guild.id}'. {sys.exc_info()[0].__name__}: {err}"
            )
            raise

    async def db_process_admin_relationship(self, member, session, server_admin):
        # Get the DB profile for the guild
        db_guild = await self.bot.helpers.db_get_guild(session, member.guild.id)
        # Get the DB profile for the user
        db_user = await self.bot.helpers.db_get_user(session, member.id)
        # If server_admin is true, then we need to add a relationship
        if server_admin:
            db_serveradminrels = models.ServerAdminRels(user=db_user, server=db_guild)
            session.add(db_serveradminrels)
            self.bot.log.debug(
                f"Server Admin Relationship Added to database: Guild: {member.guild.id}, User: {member.id}"
            )
        # Otherwise if it's false we need to remove the relationship
        else:
            session.query(models.ServerAdminRels).filter(
                models.ServerAdminRels.server_id == db_guild.id,
                models.ServerAdminRels.user_id == db_user.id,
            ).delete(synchronize_session=False)
            self.bot.log.debug(
                f"Removed admin relationship for: Guild: {member.guild.id}, User: {member.id}"
            )

    async def db_process_mod_relationship(self, member, session, server_mod):
        # Get the DB profile for the guild
        db_guild = await self.bot.helpers.db_get_guild(session, member.guild.id)
        # Get the DB profile for the user
        db_user = await self.bot.helpers.db_get_user(session, member.id)
        # If server_mod is true, then we need to add a relationship
        if server_mod:
            db_serverrels = models.ServerModRels(user=db_user, server=db_guild)
            session.add(db_serverrels)
            self.bot.log.debug(
                f"Server Mod Relationship Added to database: Guild: {member.guild.id}, User: {member.id}"
            )
        # Otherwise if it's false we need to remove the relationship
        else:
            session.query(models.ServerModRels).filter(
                models.ServerModRels.server_id == db_guild.id,
                models.ServerModRels.user_id == db_user.id,
            ).delete(synchronize_session=False)
            self.bot.log.debug(
                f"Removed mod relationship for: Guild: {member.guild.id}, User: {member.id}"
            )

    async def check_if_blacklisted(self, user_id: int, guild_id: int):
        session = self.bot.helpers.get_db_session()
        try:
            # Get the DB ID for the user
            db_user = await self.bot.helpers.db_get_user(session, user_id)
            # Get the DB ID for the guild
            db_guild = await self.bot.helpers.db_get_guild(session, guild_id)
            # Check if user is blacklisted
            user_status = (
                session.query(models.Blacklist)
                .filter(models.Blacklist.server_id == db_guild.id)
                .filter(models.Blacklist.user_id == db_user.id)
                .first()
            )

            self.bot.log.debug(
                f"Blacklist for DiscoID: {user_id}: DBID: {user_status.user_id if user_status else None} | BLStatus: {user_status.blacklisted if user_status else None}"
            )
            if not user_status or user_status.blacklisted is False:
                self.bot.log.debug(f"Blacklist for {user_id}: Allowed")
                return False
            else:
                self.bot.log.debug(f"Blacklist for {user_id}: Denied")
                return True

        except DBAPIError as err:
            self.bot.log.exception(
                f"Error processing database query for getting blacklist info. {sys.exc_info()[0].__name__}: {err}"
            )
            session.rollback()
            self.bot.log.debug(f"Blacklist for {user_id} - using default: Allowed")
            return False
        except Exception as err:
            self.bot.log.exception(
                f"Unknown exception getting blacklist info. {sys.exc_info()[0].__name__}: {err}"
            )
            self.bot.log.debug(f"Blacklist for {user_id} - using default: Allowed")
            return False
        finally:
            session.close()

    async def load_reminders(self):
        session = self.bot.helpers.get_db_session()
        try:
            reminders = (
                session.query(
                    func.coalesce(
                        models.Reminder.updated, models.Reminder.created
                    ).label("created"),
                    models.Reminder.id,
                    models.Reminder.creator_user_id,
                    models.User,
                    models.Server,
                    models.Reminder.expires,
                    models.Reminder.text,
                )
                .join(models.Server, models.Server.id == models.Reminder.server_id)
                .join(models.User, models.User.id == models.Reminder.remind_user_id)
                .filter(
                    models.Reminder.expires
                    > datetime.datetime.now(datetime.timezone.utc)
                )
                .all()
            )

            counter = 0
            temp_guild_list = [tmp_guild.id for tmp_guild in self.bot.guilds]
            for item in reminders:
                # Filter out reminders where the bot isn't in them
                if item.Server.discord_id in temp_guild_list:
                    counter += 1
                    # Add timer to send the reminder
                    timer = Timer.temporary(
                        item.Server.discord_id,
                        item.User.discord_id,
                        item.creator_user_id,
                        item.text,
                        event=self._remind,
                        expires=item.expires,
                        created=item.created,
                    )
                    timer.start(self.bot.loop)

            # Log number of reminders loaded
            self.bot.log.info(f"Loaded {counter} reminders")

        except DBAPIError as err:
            self.bot.log.exception(
                f"Error processing database query loading reminders. {sys.exc_info()[0].__name__}: {err}"
            )
            session.rollback()
        except Exception as err:
            self.bot.log.exception(
                f"Error loading reminders. {sys.exc_info()[0].__name__}: {err}"
            )
        finally:
            session.close()

    def _remind(
        self, guild_id: int, remind_user_id: int, creator_user_id: int, remind_text: str
    ):

        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                raise ValueError(f"Bot can't find guild {guild_id}")
            member = guild.get_member(remind_user_id)
            if not member:
                raise ValueError(
                    f"Bot can't find member {remind_user_id} in guild {guild} ({guild.id})"
                )
            creator_user = self.bot.get_user(creator_user_id)
        except ValueError:
            self.bot.log.exception(f"Can't execute reminder")
            raise

        settings = self.bot.guild_settings.get(member.guild.id)
        has_modmail_server = settings.modmail_server_id

        footer_text = (
            self.bot.constants.footer_with_modmail.format(guild=member.guild)
            if has_modmail_server
            else self.bot.constants.footer_no_modmail.format(guild=member.guild)
        )

        try:
            self.bot.loop.create_task(
                member.send(
                    f"Here is the reminder requested by **{creator_user}** from the **{guild}** server.\n\n'{remind_text}'{footer_text}"
                )
            )

            self.bot.log.info(
                f"Sent reminder to: {member} ({member.id}) in guild {member.guild}"
            )
        except Exception as e:
            if not (type(e) == discord.errors.Forbidden and e.code == 50007):
                self.bot.log.exception(
                    f"There was an error while informing {member} ({member.id}) about their reminder. Unable to send messages to this user."
                )
            return False

        return True


def has_guild_permissions(**perms):
    def predicate(ctx):
        author = ctx.message.author
        permissions = author.guild_permissions

        missing = [
            perm
            for perm, value in perms.items()
            if getattr(permissions, perm, None) != value
        ]

        if not missing:
            return True

        raise commands.MissingPermissions(missing)

    return commands.check(predicate)


def set_sentry_scope(ctx):
    with configure_scope() as scope:
        scope.set_extra(
            "guild_id", f"{ctx.message.guild.id if ctx.message.guild else None}"
        )
        scope.set_extra("message_id", f"{ctx.message.id if ctx.message else None}")
        scope.set_extra("command", f"{ctx.command if ctx.command else None}")
        scope.user = {
            "id": f"{ctx.message.author.id if ctx.message.author else None}",
            "username": f"{ctx.message.author if ctx.message.author else None}",
        }
