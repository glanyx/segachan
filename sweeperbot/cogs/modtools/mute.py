import datetime
import typing

import discord
from discord.ext import commands
from sqlalchemy.sql import func

from sweeperbot.cogs.utils import log, time
from sweeperbot.cogs.utils.timer import Timer
from sweeperbot.db import models
from sweeperbot.utilities.helpers import has_guild_permissions, set_sentry_scope


class Mute(commands.Cog):
    """Handle Mutes"""

    def __init__(self, bot):
        self.bot = bot
        self.current_mutes = {}

        session = self.bot.helpers.get_db_session()
        mutes = (
            session.query(
                func.coalesce(models.Mute.updated, models.Mute.created).label(
                    "created"
                ),
                models.Mute.id,
                models.User,
                models.Server,
                models.Mute.expires,
                models.Mute.old_roles,
            )
            .join(models.Server, models.Server.id == models.Mute.server_id)
            .join(models.User, models.User.id == models.Mute.user_id)
            .filter(models.Mute.expires > datetime.datetime.now(datetime.timezone.utc))
            .all()
        )

        for mute in mutes:
            # Add timer to remove mute
            timer = Timer.temporary(
                mute.Server.discord_id,
                mute.User.discord_id,
                mute.old_roles,
                event=self._unmute,
                expires=mute.expires,
                created=mute.created,
            )
            timer.start(self.bot.loop)
            if mute.Server.discord_id not in self.current_mutes:
                self.current_mutes[mute.Server.discord_id] = {}
            self.current_mutes[mute.Server.discord_id][mute.User.discord_id] = timer

        session.close()

    @commands.command(aliases=["m"])
    @has_guild_permissions(manage_messages=True)
    @commands.guild_only()
    async def mute(
        self,
        ctx,
        user_id: str,
        mute_time: time.UserFriendlyTime(commands.clean_content, default="\u2026"),
        *,
        reason: str,
    ):
        """Mute a user.

        If no time or note specified default values will be used. Time can be a human readable string, many formats are understood.

        To unmute someone see unmute

        Requires Permission: Manage Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_id: str
            The Discord ID or user mention the command is being run on.
        mute_time: time
            How long the mute will be for.
        reason: str
            The reason for the mute. This will be sent to the user and added to the logs.
        """

        self.bot.log.info(
            f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
        )

        # If we were provided an ID, let's try and use it
        if user_id:
            member = await self.bot.helpers.get_member_or_user(
                user_id, ctx.message.guild
            )
            if not member:
                return await ctx.send(
                    f"Unable to find the requested user. Please make sure the user ID or @ mention is valid."
                )
            elif isinstance(member, discord.User):
                await ctx.send(
                    f"The user specified does not appear to be in the server. Proceeding with mute in case they return."
                )
        else:
            return await ctx.send(
                f"A user ID or Mention must be provided for who to mute."
            )
        if mute_time == "20m":
            mute_time = datetime.datetime.now(
                datetime.timezone.utc
            ) + datetime.timedelta(minutes=20)
        elif isinstance(mute_time, datetime.datetime):
            mute_time = mute_time
        else:
            mute_time = mute_time.dt

        mute_length_human = time.human_timedelta(mute_time)

        settings = self.bot.guild_settings.get(ctx.message.guild.id)
        has_modmail_server = settings.modmail_server_id
        muted_role_id = settings.muted_role
        mod_channel = discord.utils.get(
            ctx.message.guild.text_channels, id=settings.mod_channel
        )
        if not mod_channel:
            await ctx.send(
                "Please set a mod channel using `config modchannel #channel`"
            )
        # delete the message we used to invoke it
        if mod_channel and ctx.message.channel.id != mod_channel.id:
            try:
                await ctx.message.delete()
            except discord.HTTPException as err:
                self.bot.log.warning(
                    f"Couldn't delete command message for {ctx.command}: {err}"
                )

        log_channel = discord.utils.get(
            ctx.message.guild.text_channels, name="bot-logs"
        )
        if not log_channel:
            # If there is no normal logs channel, try the sweeper (legacy) logs channel
            log_channel = discord.utils.get(
                ctx.message.guild.text_channels, name="sweeper-logs"
            )
            if not log_channel:
                return await ctx.send(
                    f"No log channel setup. Please create a channel called #bot-logs"
                )

        muted_role = ctx.message.guild.get_role(muted_role_id)
        if not muted_role:
            return await ctx.send("Mute role is not yet configured. Unable to proceed.")

        footer_text = (
            self.bot.constants.footer_with_modmail.format(guild=ctx.message.guild)
            if has_modmail_server
            else self.bot.constants.footer_no_modmail.format(guild=ctx.message.guild)
        )

        sweeper_emoji = self.bot.get_emoji(
            self.bot.constants.reactions["animated_sweeperbot"]
        )

        session = self.bot.helpers.get_db_session()
        try:
            old_mute_len = None
            old_mute_dt = None
            if not isinstance(member, discord.User):
                if muted_role in member.roles:
                    if (
                        ctx.message.guild.id in self.current_mutes
                        and member.id in self.current_mutes[ctx.message.guild.id]
                    ):
                        old_mute_len = self.current_mutes[ctx.message.guild.id][
                            member.id
                        ].human_delta
                        old_mute_dt = self.current_mutes[ctx.message.guild.id][
                            member.id
                        ].expires
                        self.current_mutes[ctx.message.guild.id][member.id].stop()
                        del self.current_mutes[ctx.message.guild.id][member.id]

                if (
                    member is ctx.message.guild.owner
                    or member.bot
                    or member is ctx.message.author
                ):
                    return await ctx.send("You may not use this command on that user.")

                if member.top_role > ctx.me.top_role:
                    return await ctx.send(
                        "The user has higher permissions than the bot, can't use this command on that user."
                    )

            actionMsg = await ctx.send("Initiating action. Please wait.")
            self.bot.log.info(
                f"Initiating mute for user: {member} ({member.id}) in guild {ctx.message.guild} ({ctx.message.guild.id})"
            )

            old_roles = []
            old_roles_snow = []
            if not isinstance(member, discord.User):
                for role in member.roles:
                    if role.managed or role.name == "@everyone":
                        continue
                    else:
                        old_roles_snow.append(role)
                        old_roles.append(role.id)

                # Remove all non-managed roles
                await member.remove_roles(
                    *old_roles_snow,
                    reason=f"Muted by request of {ctx.message.author} ({ctx.message.author.id})",
                    atomic=True,
                )
                # Assign mute role
                await member.add_roles(
                    muted_role,
                    reason=f"Muted by request of {ctx.message.author} ({ctx.message.author.id})",
                    atomic=True,
                )
                # If in voice, kick
                try:
                    if member.voice and member.voice.channel:
                        await member.move_to(
                            channel=None,
                            reason=f"Muted by request of {ctx.message.author.mention}",
                        )
                except discord.errors.Forbidden:
                    await ctx.send(
                        f"Missing permissions to drop user from voice channel."
                    )

            self.bot.log.info(
                f"Muted user: {member} ({member.id}) in guild {ctx.message.guild} ({ctx.message.guild.id}) for {mute_length_human}"
            )
            informed_user = False
            try:
                # Format the message
                text = self.bot.constants.infraction_header.format(
                    action_type="mute", guild=ctx.message.guild
                )

                # Reduces the text to 1,800 characters to leave enough buffer for header and footer text
                text += f"This mute is for **{mute_length_human}** with the reason:\n\n"
                text += reason[:1800]
                text += footer_text
                await member.send(text)
                self.bot.log.info(
                    f"Informed user of their mute: {member} ({member.id}) in guild {ctx.message.guild}"
                )
                informed_user = True
                if mod_channel and actionMsg.channel.id == mod_channel.id:
                    await actionMsg.edit(
                        content=f"Mute successful for {member.mention}. **Time:** *{mute_length_human}*. {sweeper_emoji}"
                    )
                    if old_mute_len:
                        await ctx.send(
                            f"**Note**: This user was previously muted until {old_mute_len}."
                        )
                else:
                    await actionMsg.edit(
                        content=f"That action was successful. {sweeper_emoji}"
                    )
            except Exception as e:
                if mod_channel:
                    await mod_channel.send(
                        f"Mute successful for {member.mention}. **Time:** *{mute_length_human}*. {sweeper_emoji}\n"
                        f"However, user couldn't be informed: {e}"
                    )
                if not (type(e) == discord.errors.Forbidden and e.code == 50007):
                    self.bot.log.exception(
                        f"There was an error while informing {member} ({member.id}) about their mute"
                    )

            if informed_user:
                reason += "| **Msg Delivered: Yes**"
            else:
                reason += "| **Msg Delivered: No**"

            # Log action
            await log.user_action(
                self.bot,
                log_channel.name,
                member,
                "Mute",
                f"**Length:** {mute_length_human}\n" f"**Reason:** {reason}",
                ctx.message.author,
                ctx.message.guild,
            )

            # Get the DB profile for the guild
            db_guild = await self.bot.helpers.db_get_guild(
                session, ctx.message.guild.id
            )
            # Get the DB profile for the user
            db_user = await self.bot.helpers.db_get_user(session, member.id)
            # Get mod's DB profile
            db_mod = await self.bot.helpers.db_get_user(session, ctx.message.author.id)
            db_action = models.Action(mod=db_mod, server=db_guild)

            db_mute = None
            if old_mute_len:
                db_mute = (
                    session.query(models.Mute)
                    .filter(models.Mute.server == db_guild)
                    .filter(models.Mute.user == db_user)
                    .filter(models.Mute.expires == old_mute_dt)
                    .one_or_none()
                )
            if db_mute:
                session.add(db_action)
                session.commit()

                db_mute.action_id = db_action.id
                db_mute.text = reason
                db_mute.expires = mute_time
                db_mute.updated = datetime.datetime.now(datetime.timezone.utc)
            else:
                db_mute = models.Mute(
                    text=reason,
                    user=db_user,
                    server=db_guild,
                    action=db_action,
                    expires=mute_time,
                    old_roles=old_roles,
                )
            session.add(db_mute)
            session.commit()

            # Add timer to remove mute
            timer = Timer.temporary(
                ctx.message.guild.id,
                member.id,
                old_roles,
                event=self._unmute,
                expires=mute_time,
                created=datetime.datetime.now(datetime.timezone.utc),
            )
            timer.start(self.bot.loop)
            if ctx.message.guild.id not in self.current_mutes:
                self.current_mutes[ctx.message.guild.id] = {}
            self.current_mutes[ctx.message.guild.id][member.id] = timer

        except Exception as e:
            set_sentry_scope(ctx)
            if mod_channel:
                await mod_channel.send(
                    f"There was an error while creating mute for {member.mention}\n"
                    f"**Error**: {e}"
                )
            self.bot.log.exception(
                f"There was an error while creating mute for {member} ({member.id})"
            )
        finally:
            session.close()

    @commands.command(aliases=["um"])
    @has_guild_permissions(manage_messages=True)
    @commands.guild_only()
    async def unmute(self, ctx, member: discord.Member):
        """Removes a mute for specified user.

        To Mute someone see mute
        """

        self.bot.log.info(
            f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
        )

        settings = self.bot.guild_settings.get(ctx.message.guild.id)
        muted_role_id = settings.muted_role
        muted_role = member.guild.get_role(muted_role_id)
        mod_channel = discord.utils.get(
            ctx.message.guild.text_channels, id=settings.mod_channel
        )
        if not mod_channel:
            await ctx.send(
                "Please set a mod channel using `config modchannel #channel`"
            )
        # delete the message we used to invoke it
        if mod_channel and ctx.message.channel.id != mod_channel.id:
            try:
                await ctx.message.delete()
            except discord.HTTPException as err:
                self.bot.log.warning(
                    f"Couldn't delete command message for {ctx.command}: {err}"
                )

        session = self.bot.helpers.get_db_session()
        try:
            if muted_role is None:
                return await ctx.send("Mute role is not yet configured.")

            if muted_role not in member.roles:
                return await ctx.send("User is not muted")

            if (
                member is member.guild.owner
                or member.bot
                or member is ctx.message.author
            ):
                return await ctx.send("You may not use this command on that user.")

            old_mute_dt = None
            old_roles = []
            if (
                member.guild.id in self.current_mutes
                and member.id in self.current_mutes[member.guild.id]
            ):
                old_mute_dt = self.current_mutes[member.guild.id][member.id].expires
                query = (
                    session.query(models.Mute.old_roles)
                    .filter(models.Mute.expires == old_mute_dt)
                    .first()
                )
                if query:
                    old_roles = query.old_roles

            if self._unmute(member.guild.id, member.id, old_roles, ctx.message.author):
                if ctx.message.channel.id == mod_channel.id:
                    await ctx.send(f"Successfully unmuted {member.mention}.")
                else:
                    await ctx.send(f"That action was successful.")
            else:
                await mod_channel.send(
                    f"Successfully unmuted {member.mention}. However, user could not be informed."
                )

            if old_mute_dt:
                # Get the DB profile for the guild
                db_guild = await self.bot.helpers.db_get_guild(
                    session, ctx.message.guild.id
                )
                # Get the DB profile for the user
                db_user = await self.bot.helpers.db_get_user(session, member.id)
                # Get mod's DB profile
                db_mod = await self.bot.helpers.db_get_user(
                    session, ctx.message.author.id
                )
                db_action = models.Action(mod=db_mod, server=db_guild)

                db_mute = (
                    session.query(models.Mute)
                    .filter(models.Mute.server == db_guild)
                    .filter(models.Mute.user == db_user)
                    .filter(models.Mute.expires == old_mute_dt)
                    .one_or_none()
                )
                if db_mute:
                    session.add(db_action)
                    session.commit()

                    db_mute.action_id = db_action.id
                    db_mute.expires = datetime.datetime.now(datetime.timezone.utc)
                    db_mute.updated = datetime.datetime.now(datetime.timezone.utc)
                    session.add(db_mute)
                    session.commit()
                else:
                    self.bot.log.warning(
                        f"Couldn't find mute for {member} ({member.id}) in database"
                    )
            else:
                self.bot.log.warning(
                    f"Couldn't find mute for {member} ({member.id}) in currently active mutes"
                )

        except Exception as e:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"There was an error while unmuting {member} ({member.id})"
            )
            await mod_channel.send(
                f"There was an error while unmuting {member.mention}\n"
                f"**Error**: {e}"
            )
        finally:
            session.close()

    def _unmute(
        self,
        guild_id: int,
        member_id: int,
        old_roles: typing.List[int],
        author: typing.Optional[discord.Member] = None,
    ):
        if guild_id in self.current_mutes and member_id in self.current_mutes[guild_id]:
            self.current_mutes[guild_id][member_id].stop()
            del self.current_mutes[guild_id][member_id]

        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                raise ValueError(f"Bot can't find guild {guild_id}")
            member = guild.get_member(member_id)
            if not member:
                raise ValueError(
                    f"Bot can't find member {member_id} in guild {guild} ({guild.id})"
                )
        except ValueError:
            self.bot.log.warning(f"Can't execute unmute")
            raise

        settings = self.bot.guild_settings.get(member.guild.id)
        has_modmail_server = settings.modmail_server_id
        muted_role_id = settings.muted_role
        muted_role = member.guild.get_role(muted_role_id)

        footer_text = (
            self.bot.constants.footer_with_modmail.format(guild=member.guild)
            if has_modmail_server
            else self.bot.constants.footer_no_modmail.format(guild=member.guild)
        )

        # If they had roles prior to the mute, add them back
        if old_roles:
            old_disc_roles = []
            for role_id in old_roles:
                # Check if the role exists in the server prior to trying to add it back
                temp_role = member.guild.get_role(role_id)
                if temp_role:
                    old_disc_roles.append(temp_role)

            # Get their current/managed roles
            current_roles = member.roles
            # Remove the muted role from that list, leaving us with the managed roles like Nitro Booster or Twitch
            # Streamer roles which we can't remove. We're going to tell discord to "Add" these back in the member.edit()
            # Which will allow us to give them their old roles back while removing the muted role
            current_roles.remove(muted_role)
            for role in current_roles:
                old_disc_roles.append(role)
            # now we create the task to set their roles to the old+managed roles thus removing the muted role
            self.bot.loop.create_task(
                member.edit(
                    roles=old_disc_roles,
                    reason=f"Adding roles back and removing muted role after unmute",
                )
            )
        else:
            self.bot.loop.create_task(
                member.remove_roles(
                    muted_role, reason="Removing muted role after unmute"
                )
            )

        # Log action
        self.bot.loop.create_task(
            log.user_action(self.bot, "bot-logs", member, "Unmute")
        )
        self.bot.log.info(
            f"Removed mute for {member} ({member.id}) in guild {member.guild}"
        )

        try:
            self.bot.loop.create_task(
                member.send(
                    f"You have been unmuted on {member.guild}. You may now send messages."
                    f"{footer_text}"
                )
            )
            self.bot.log.info(
                f"Informed user of their unmute: {member} ({member.id}) in guild {member.guild}"
            )
        except Exception as e:
            if not (type(e) == discord.errors.Forbidden and e.code == 50007):
                self.bot.log.exception(
                    f"There was an error while informing {member} ({member.id}) about their unmute"
                )
            return False

        return True

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if (
            member.guild.id not in self.current_mutes
            or member.id not in self.current_mutes[member.guild.id]
        ):
            return

        # Member has a muting timer
        timer = self.current_mutes[member.guild.id][member.id]
        if not timer:
            del self.current_mutes[member.guild.id][member.id]
            return

        # Member has an active muting timer

        settings = self.bot.guild_settings.get(member.guild.id)
        has_modmail_server = settings.modmail_server_id
        muted_role_id = settings.muted_role
        muted_role = member.guild.get_role(muted_role_id)

        footer_text = (
            self.bot.constants.footer_with_modmail.format(guild=member.guild)
            if has_modmail_server
            else self.bot.constants.footer_no_modmail.format(guild=member.guild)
        )

        # Assign mute role & mute in voice
        await member.edit(
            # mute=True,
            roles=[muted_role],
            reason=f"Re-mute after server rejoin",
        )

        self.bot.log.info(
            f"Remuted rejoined user: {member} ({member.id}) in guild {member.guild} for {timer.human_delta}"
        )
        try:
            await member.send(
                f"You are still muted on **{member.guild}** for **{timer.human_delta}**."
                f"{footer_text}"
            )
            self.bot.log.info(
                f"Informed user of their mute: {member} ({member.id}) in guild {member.guild}"
            )
        except Exception as e:
            if not (type(e) == discord.errors.Forbidden and e.code == 50007):
                self.bot.log.exception(
                    f"There was an error while informing {member} ({member.id}) about their continued mute"
                )

        # Log action
        await log.user_action(
            self.bot,
            "bot-logs",
            member,
            "Mute",
            f"**Length:** {timer.human_delta}\n" f"**Reason:** Remuted after rejoin",
        )


def setup(bot):
    bot.add_cog(Mute(bot))
