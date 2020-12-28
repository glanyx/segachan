import datetime
import sys

import discord
from discord.ext import commands
from sqlalchemy.exc import DBAPIError
from sqlalchemy.sql import func

from sweeperbot.cogs.utils import time
from sweeperbot.cogs.utils.timer import Timer
from sweeperbot.db import models
from sweeperbot.utilities.helpers import set_sentry_scope


class Reminder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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

    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @commands.command()
    @commands.cooldown(3, 120, commands.BucketType.user)
    async def remind(
        self,
        ctx,
        remind_user: str,
        remind_time: time.UserFriendlyTime(commands.clean_content, default="\u2026"),
        *,
        remind_text: str,
    ):
        """Creates a reminder that the bot will remind you of. If the person creating the reminder has 'Manage Messages' permission then any user or role pings will be left alone. If they don't (aka regular user) then the user and role pings will be not be allowed.

        Things to figure out/do
        - Does it DM the user the reminder or put it in chat? What if it has a role mention, that we'd want in chat 'remind me in 1day There is a @moderators meeting'
        - Create a delete reminder command - use note delete as an example
        - Future: Allow it to recognize time in format of datestamp vs duration

        Requires Permission: Send Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        remind_user: str
            The user the reminder is for. For self can use 'me' or a user mention or user ID of someone else.
        remind_time: time
            When to be reminded. Format of 1m (minute), 2h (hours), 3d (days), 4mo (months), 5y (years)
        remind_text: str
            The text to be reminded of.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            # Check if user is blacklisted, if so, ignore.
            if await self.bot.helpers.check_if_blacklisted(
                ctx.message.author.id, ctx.message.guild.id
            ):
                self.bot.log.debug(
                    f"User {ctx.message.author} ({ctx.message.author.id}) Blacklisted, unable to use command {ctx.command}"
                )
                return

            # If we were provided an ID, let's try and use it
            if remind_user.lower() in ["me", "myself"]:
                remind_user = ctx.message.author
            else:
                remind_user = await self.bot.helpers.get_member_or_user(
                    remind_user, ctx.message.guild
                )
                if not remind_user:
                    return await ctx.send(
                        f"Sorry, I am unable to find the person you are trying to set the reminder for. Please make sure you are using a proper @ mention of the user or their User ID."
                    )

            # Variables used for the database/later on
            creator_user = ctx.message.author
            remind_time = remind_time.dt
            guild = ctx.message.guild

            # Save in the database
            # Get the DB profile for the guild
            db_guild = await self.bot.helpers.db_get_guild(session, guild.id)
            # Get the DB profile for the remind_user
            db_remind_user = await self.bot.helpers.db_get_user(session, remind_user.id)
            # DB Entry
            db_remind = models.Reminder(
                creator_user_id=ctx.message.author.id,
                remind_user=db_remind_user,
                server=db_guild,
                expires=remind_time,
                text=remind_text,
            )
            session.add(db_remind)
            session.commit()

            # Add timer to send the reminder
            timer = Timer.temporary(
                guild.id,
                remind_user.id,
                creator_user.id,
                remind_text,
                event=self._remind,
                expires=remind_time,
                created=datetime.datetime.now(datetime.timezone.utc),
            )
            timer.start(self.bot.loop)

            # Tell user reminder is created
            # TO DO - Make this look a little nicer.
            await ctx.send(
                f"{ctx.message.author.mention}, I have now created the reminder for {remind_user.mention}."
            )

        except discord.HTTPException as err:
            set_sentry_scope(ctx)
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request. {sys.exc_info()[0].__name__}: {err}"
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
                f"Error responding to {ctx.command}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        finally:
            session.close()

    @commands.has_permissions(send_messages=True)
    @commands.guild_only()
    @commands.command()
    async def reminders(self, ctx):
        """Sends you a DM with a list of all reminders for you."""

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            # Check if user is blacklisted, if so, ignore.
            if await self.bot.helpers.check_if_blacklisted(
                ctx.message.author.id, ctx.message.guild.id
            ):
                self.bot.log.debug(
                    f"User {ctx.message.author} ({ctx.message.author.id}) Blacklisted, unable to use command {ctx.command}"
                )
                return

            # Get the DB profile for the remind_user
            db_remind_user = await self.bot.helpers.db_get_user(
                session, ctx.message.author.id
            )

            reminders = (
                session.query(
                    func.coalesce(
                        models.Reminder.updated, models.Reminder.created
                    ).label("created"),
                    models.Reminder.id,
                    models.Reminder.creator_user_id,
                    models.Reminder.remind_user_id,
                    models.Server,
                    models.Reminder.expires,
                    models.Reminder.text,
                )
                .join(models.Server, models.Server.id == models.Reminder.server_id)
                .filter(
                    models.Reminder.expires
                    > datetime.datetime.now(datetime.timezone.utc),
                    models.Reminder.remind_user_id == db_remind_user.id,
                )
                .all()
            )

            # TO DO - Use pagination to accomplish this - look at tag list command for example
            msg_text = ""
            for item in reminders:
                msg_text += f"{item.id}. **Expires**: [{item.expires} UTC]\n**Reminder Text:** [{item.text}]\n"

            await ctx.message.author.send(
                f"Here's a list of your reminders:\n\n{msg_text if len(reminders) >0 else 'You do not have any reminders.'}"
            )
        except discord.HTTPException as err:
            set_sentry_scope(ctx)
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command}. {sys.exc_info()[0].__name__}: {err}"
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
                f"Error responding to {ctx.command}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        finally:
            session.close()


def setup(bot):
    bot.add_cog(Reminder(bot))
