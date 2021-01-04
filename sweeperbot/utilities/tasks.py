import asyncio
import sys
import random

import discord
from sqlalchemy.exc import DBAPIError

from sweeperbot.db import models


class Tasks:
    def __init__(self, bot):
        self.bot = bot
        self.all_tasks = []
        self.loaded = False

    async def start_tasks(self):
        # Internal check if we've already loaded and started the tasks
        if self.loaded:
            self.bot.log.debug(f"Already loaded start_tasks, skipping")
            return
        # Log Server Stats
        task_server_stats = asyncio.create_task(self.log_server_stats())
        self.all_tasks.append(task_server_stats)
        # Change activity status
        task_activity_status = asyncio.create_task(self.change_activity_status())
        self.all_tasks.append(task_activity_status)
        # Load antispam services from db
        task_load_antispam_services = asyncio.create_task(
            self.load_antispam_services_from_db()
        )
        self.all_tasks.append(task_load_antispam_services)
        self.bot.log.info(f"Loaded start_tasks")

    async def log_server_stats(self):
        while True:
            for guild in self.bot.guilds:
                # If the guild is unavailable such as during an outage, skip it
                if guild and guild.unavailable:
                    continue
                # Get DB Session
                session = self.bot.helpers.get_db_session()
                try:
                    # Check if there is a guild in the database already
                    db_guild = (
                        session.query(models.Server)
                        .filter(models.Server.discord_id == guild.id)
                        .first()
                    )
                    if not db_guild:
                        db_guild = await self.bot.helpers.db_add_new_guild(
                            session, guild.id, guild
                        )

                    # Set default options in case the we can't get more accurate info:
                    member_count = guild.member_count
                    presence_count = 0  # Sadly only way to get any remotely accurate presence is via invite code
                    voice_channels = guild.voice_channels or []
                    # Get guild invite
                    invite = await self.bot.helpers.get_guild_invite(guild)

                    if invite:
                        member_count = invite.approximate_member_count
                        presence_count = invite.approximate_presence_count

                    data = {
                        "total_users": member_count,
                        "concurrent_users": presence_count,
                        "total_voice_users": sum(
                            len(vc.members or []) for vc in voice_channels
                        ),
                    }
                    new_stat = models.Statistic(server=db_guild, **data)
                    session.add(new_stat)
                    session.commit()
                    self.bot.log.debug(
                        f"Logged server stats for: {guild.name} ({guild.id}) | Data: {data}"
                    )

                except DBAPIError as err:
                    self.bot.log.exception(
                        f"Database Error logging Server Stats. {sys.exc_info()[0].__name__}: {err}"
                    )
                    session.rollback()
                except Exception as err:
                    self.bot.log.exception(
                        f"Generic Error logging Server Stats. {sys.exc_info()[0].__name__}: {err}"
                    )
                finally:
                    # Close this database session
                    session.close()
            # Time in seconds. Currently 5 minutes
            await asyncio.sleep(60 * 5)

    async def change_activity_status(self):
        # Wait 30 seconds for bot to load, then set status
        await asyncio.sleep(30)
        while True:
            for guild in self.bot.guilds:
                # If the guild is unavailable such as during an outage, skip it
                if guild and guild.unavailable:
                    continue

                try:
                    settings = self.bot.guild_settings.get(guild.id)
                    if not settings:
                        self.bot.log.debug(
                            f"Tasks (activity status): No settings for guild: {guild.id}"
                        )
                        continue
                    activity_status = settings.activity_status
                    activity_status_enabled = settings.activity_status_enabled

                    if not activity_status_enabled:
                        continue

                    # If there is at least one activity status text added
                    if len(activity_status) > 0:

                        # Get a random activity status text
                        activity_text = str(random.choice(activity_status))

                        # If length of stripping the text is blank, skip trying to set the status, discord would reject
                        if len(activity_text.strip()) == 0:
                            print(f"{activity_text.strip()}")
                            continue
                        # Set the activity status
                        try:
                            await self.bot.change_presence(
                                activity=discord.Game(name=f"{activity_text}")
                            )
                            self.bot.log.debug(
                                f"Tasks: Set Activity Text to: '{activity_text}' from Guild: {guild.id}"
                            )
                        except Exception as err:
                            self.bot.log.exception(
                                f"Tasks: Failed to set presence info. {sys.exc_info()[0].__name__}: {err}"
                            )

                except Exception as err:
                    self.bot.log.exception(
                        f"Tasks: Generic Error setting presence info. {sys.exc_info()[0].__name__}: {err}"
                    )
            # Time in seconds. Currently 10 minutes
            await asyncio.sleep(60 * 10)

    async def load_antispam_services_from_db(self):
        while True:
            session = self.bot.helpers.get_db_session()
            try:
                self.bot.antispam.antispam_services = (
                    session.query(models.AntiSpamServices)
                    .filter(models.AntiSpamServices.enabled.is_(True))
                    .all()
                )
                self.bot.log.info(f"Loaded AntiSpam Services from DB")
            except DBAPIError as err:
                self.bot.log.exception(
                    f"Database Error loading AntiSpam Module. {sys.exc_info()[0].__name__}: {err}"
                )
                session.rollback()
            finally:
                # Close this database session
                session.close()
                # Wait before looping again. Time in seconds. Currently 10 minutes
                await asyncio.sleep(60 * 10)

    async def cancel_all_tasks(self):
        for task in self.all_tasks:
            try:
                self.bot.log.info(f"Tasks: Attempting to cancel: {task}")
                task.cancel()
            except asyncio.CancelledError:
                self.bot.log.info(f"Tasks: Cancelled: {task}")
            except Exception as err:
                self.bot.log.exception(
                    f"Tasks: Not sure how this happened.. some error cancelling the task: {sys.exc_info()[0].__name__}: {err}"
                )
