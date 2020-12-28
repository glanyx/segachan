import sys

import discord
from discord.ext import commands
from sqlalchemy import exc

from sweeperbot.cogs.utils.paginator import FieldPages
from sweeperbot.db import models


class Config(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.group(
        name="Config.Server",
        aliases=["svrconfig", "svrconfigure", "configure", "config"],
        case_insensitive=True,
        invoke_without_command=False,
    )
    async def config(self, ctx):
        """Allows for setting various server configuration."""
        pass

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @config.command(aliases=["mutedrole", "muteroles", "mutedroles"])
    async def muterole(self, ctx, *, mute_role: str):
        """Sets the muted role used by the mute command which is assigned to a user when they are muted.

        Example:

        config muterole role name
        config muterole role_id

        Requires Permission: Manage Guild

        Parameters
        -----------
        ctx: context
            The context message involved.
        mute_role: str
            Role name or ID of the role the bot will give when a user is muted.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # Get the muted role
            muterole = discord.utils.find(
                lambda r: r.name.lower() == mute_role.lower().strip(),
                ctx.message.guild.roles,
            )

            if not muterole:
                return await ctx.message.author.send(
                    f"Unable to find a role named `{mute_role}`"
                )

            # Get the guild settings and update the muted role
            settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            settings.muted_role = muterole.id
            session.commit()

            # Update local cache
            self.bot.guild_settings[
                ctx.message.guild.id
            ] = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            return await ctx.send(
                f"Successfully set the muted role to: {muterole.mention}."
            )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error with {ctx.command} command. {sys.exc_info()[0].__name__}: {err}"
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

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @config.command(aliases=["modchannels"])
    async def modchannel(self, ctx, *, channel: discord.TextChannel):
        """Sets the mod channel used by the bot for major alerts.

        Example:

        config modchannel #channel_name

        Requires Permission: Manage Guild

        Parameters
        -----------
        ctx: context
            The context message involved.
        channel: discord.TextChannel
            Channel designated as the mod channel for major alerts.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # Get the guild settings and update the channel id
            settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            settings.mod_channel = channel.id
            session.commit()

            # Update local cache
            self.bot.guild_settings[
                ctx.message.guild.id
            ] = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            return await ctx.send(
                f"Successfully set the mod channel to: {channel.mention}."
            )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error with {ctx.command} command. {sys.exc_info()[0].__name__}: {err}"
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

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @config.command()
    async def adminrole(self, ctx, *, role_name: str):
        """Sets the Admin role which is used for permissions access on the website. This will also do a sync of the admins currently in that role.

        Example:

        config adminrole role name

        Requires Permission: Manage Guild

        Parameters
        -----------
        ctx: context
            The context message involved.
        role_name: str
            The role name that cooresponds to the Admin role
        """
        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # If user tries to mention @everyone then deny it.
            if role_name.lower() == "@everyone":
                return await ctx.message.author.send(
                    f"Sorry, but we can't allow you to set the role to everyone."
                )

            # Finds the role, case-insensitive removing leading and trailing whitespace.
            role = discord.utils.find(
                lambda r: r.name.lower() == role_name.lower().strip(),
                ctx.message.guild.roles,
            )

            if not role:
                return await ctx.message.author.send(
                    f"Unable to find a role named `{role_name}`"
                )

            # Now that we have the role, let them know we're about to start
            await ctx.send(f"About to set the admin role and start the initial sync")
            # Get the guild settings and update the id
            # Get current settings stored from the database
            guild_settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            guild_settings.admin_role = role.id

            # Update local cache
            self.bot.guild_settings[
                ctx.message.guild.id
            ] = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            # Now that we have the role, let's update the list of admins
            # We're going to start by removing all admins for the server and setting new ones. This is due to the fact
            # that the server may be changing the admin role, and we don't want any old/bad data.
            # Get the DB profile for the guild
            db_guild = await self.bot.helpers.db_get_guild(
                session, ctx.message.guild.id
            )
            rels = (
                session.query(models.ServerAdminRels)
                .filter(models.ServerAdminRels.server_id == db_guild.id)
                .all()
            )
            # Now let's make sure it's for the server we want
            if rels:
                for relationship in rels:
                    if relationship.server_id == db_guild.id:
                        self.bot.log.debug(
                            f"About to delete admin rel: Guild: {relationship.server_id} | User: {relationship.user_id} | Msg ID: {ctx.message.id}"
                        )
                        session.delete(relationship)
                    else:
                        self.bot.log.debug(
                            f"Skipping admin rel delete: Guild: {relationship.server_id} | User: {relationship.user_id} | Msg ID: {ctx.message.id}"
                        )

            # After which let's add the new admins
            members = role.members
            for member in members:
                try:
                    await self.bot.helpers.db_process_admin_relationship(
                        member, session, True
                    )
                except exc.IntegrityError:
                    self.bot.log.warning(
                        f"Duplicate Server Admin Relationship record for member {member} ({member.id}), ignoring"
                    )
                    session.rollback()

            # Now that the sync/setup is done, let's commit all our changes
            session.commit()
            # and let the user know we're done
            await ctx.send(f"Config and sync of admin role is complete.")

        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error with {ctx.command} command. {sys.exc_info()[0].__name__}: {err}"
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

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @config.command()
    async def modrole(self, ctx, *, role_name: str):
        """Sets the Mod role which is used for permissions access on the website. This will also do a sync of the mods currently in that role.

        Example:

        config modrole role name

        Requires Permission: Manage Guild

        Parameters
        -----------
        ctx: context
            The context message involved.
        role_name: str
            The role name that corresponds to the Mod role
        """
        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # If user tries to mention @everyone then deny it.
            if role_name.lower() == "@everyone":
                return await ctx.message.author.send(
                    f"Sorry, but we can't allow you to set the role to everyone."
                )

            # Finds the role, case-insensitive removing leading and trailing whitespace.
            role = discord.utils.find(
                lambda r: r.name.lower() == role_name.lower().strip(),
                ctx.message.guild.roles,
            )

            if not role:
                return await ctx.message.author.send(
                    f"Unable to find a role named `{role_name}`"
                )

            # Now that we have the role, let them know we're about to start
            await ctx.send(f"About to set the mod role and start the initial sync")
            # Get the guild settings and update the id
            # Get current settings stored from the database
            guild_settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            guild_settings.mod_role = role.id

            # Update local cache
            self.bot.guild_settings[
                ctx.message.guild.id
            ] = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            # Now that we have the role, let's update the list of admins
            # We're going to start by removing all admins for the server and setting new ones. This is due to the fact
            # that the server may be changing the admin role, and we don't want any old/bad data.
            # Get the DB profile for the guild
            db_guild = await self.bot.helpers.db_get_guild(
                session, ctx.message.guild.id
            )
            rels = (
                session.query(models.ServerModRels)
                .filter(models.ServerModRels.server_id == db_guild.id)
                .all()
            )
            # Now let's make sure it's for the server we want
            if rels:
                for relationship in rels:
                    if relationship.server_id == db_guild.id:
                        self.bot.log.debug(
                            f"About to delete mod rel: Guild: {relationship.server_id} | User: {relationship.user_id} | Msg ID: {ctx.message.id}"
                        )
                        session.delete(relationship)
                    else:
                        self.bot.log.debug(
                            f"Skipping mod rel delete: Guild: {relationship.server_id} | User: {relationship.user_id} | Msg ID: {ctx.message.id}"
                        )

            # After which let's add the new admins
            members = role.members
            for member in members:
                try:
                    await self.bot.helpers.db_process_mod_relationship(
                        member, session, True
                    )
                except exc.IntegrityError:
                    self.bot.log.warning(
                        f"Duplicate Server Mod Relationship record for member {member} ({member.id}), ignoring"
                    )
                    session.rollback()

            # Now that the sync/setup is done, let's commit all our changes
            session.commit()
            # and let the user know we're done
            await ctx.send(f"Config and sync of mod role is complete.")

        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error with {ctx.command} command. {sys.exc_info()[0].__name__}: {err}"
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

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @config.command(aliases=["appeal"])
    async def appeals(self, ctx, *, invite: str):
        """Sets the Discord Invite to send to users for an Appeals server, a shared server so they can reach the mod team.

        Example:

        config appeals https://discord.gg/InviteCode

        Requires Permission: Manage Guild

        Parameters
        -----------
        ctx: context
            The context message involved.
        invite: str
            The full Discord invite link
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # Get the guild settings and update the channel id
            settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            settings.appeals_invite_code = invite
            session.commit()

            # Update local cache
            self.bot.guild_settings[
                ctx.message.guild.id
            ] = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            return await ctx.send(
                f"Successfully set the Appeals Server link to: {invite}."
            )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error with {ctx.command} command. {sys.exc_info()[0].__name__}: {err}"
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

    # Suggestion Configuration
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @config.group(invoke_without_command=False)
    async def suggestion(self, ctx):
        """Base for the Suggestion configuration. See `suggestion channel` and `suggestino commands`"""
        pass

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @suggestion.command(aliases=["feed", "board", "channel"])
    async def suggestion_feed_channel(self, ctx, *, channel: discord.TextChannel):
        """Sets the suggestion channel which is where suggestions get sent to.

        Example:

        config suggestion feed #channel
        config suggestion board #channel
        config suggestion channel #channel

        Requires Permission: Manage Guild

        Parameters
        -----------
        ctx: context
            The context message involved.
        channel: discord.TextChannel
            The channel mention.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # Get the guild settings and update the channel id
            settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            settings.suggestion_channel = channel.id
            session.commit()

            # Update local cache
            self.bot.guild_settings[
                ctx.message.guild.id
            ] = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            return await ctx.send(
                f"Successfully set the channel where suggestions are sent to: {channel.mention}."
            )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error with {ctx.command} command. {sys.exc_info()[0].__name__}: {err}"
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

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @suggestion.command(aliases=["commands"])
    async def suggestion_channel_allowed(self, ctx, *, channel: discord.TextChannel):
        """Sets the channel that users are allowed to use the suggestion command in.

        Example:

        config suggestion commands #channel

        Requires Permission: Manage Guild

        Parameters
        -----------
        ctx: context
            The context message involved.
        channel: discord.TextChannel
            The channel mention.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # Get the guild settings
            settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            settings.suggestion_channel_allowed = [channel.id]
            session.commit()

            # Update local cache
            self.bot.guild_settings[
                ctx.message.guild.id
            ] = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            return await ctx.send(
                f"Successfully set the channel users are allowed to use the suggestion command in to: {channel.mention}."
            )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error with {ctx.command} command. {sys.exc_info()[0].__name__}: {err}"
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

    # AntiSpam Configuration
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @config.group(aliases=["spam"], invoke_without_command=False)
    async def antispam(self, ctx):
        """Base for the Antispam configuration. See `antispam quickmsg true/false`"""
        pass

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @antispam.command(aliases=["quickmessage"])
    async def quickmsg(self, ctx, *, enabled: bool):
        """Sets whether the quick message antispam feature is enabled or not.

        Example:

        config antispam quickmsg true
        config antispam quickmsg false

        Requires Permission: Manage Guild

        Parameters
        -----------
        ctx: context
            The context message involved.
        enabled: bool
            Whether to enable the feature.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # Get the guild settings
            settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            settings.antispam_quickmsg = enabled
            session.commit()

            # Update local cache
            self.bot.guild_settings[
                ctx.message.guild.id
            ] = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            return await ctx.send(
                f"Successfully set the AntiSpam Quick Message feature to: {enabled}."
            )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error with {ctx.command} command. {sys.exc_info()[0].__name__}: {err}"
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

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @antispam.command(aliases=["rate"])
    async def antispam_rate(self, ctx, *, rate: int):
        """Sets the antispam on_message rate (how many messages) can be sent (whole number only). Be sure to set the `antispam time` value for per *seconds* the rate is for.

        Example:

        config antispam rate 4

        Requires Permission: Manage Guild

        Parameters
        -----------
        ctx: context
            The context message involved.
        rate: int
            How many messages can be set before being triggered. Whole numbers only.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # Get the guild settings
            settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            settings.cd_on_message_rate = rate
            session.commit()

            # Update local cache
            self.bot.guild_settings[
                ctx.message.guild.id
            ] = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            # Reinitialize all the cooldowns and their buckets
            await self.bot.antispam.set_cooldown_buckets()

            return await ctx.send(
                f"Successfully set the AntiSpam On Message # of Messages rate to: {rate}."
            )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error with {ctx.command} command. {sys.exc_info()[0].__name__}: {err}"
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

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @antispam.command(aliases=["per", "time", "timer"])
    async def antispam_timer(self, ctx, *, rate: float):
        """Sets the antispam on_message timeout (in seconds). This is how many seconds the messages must be sent in before being triggered. Be sure to set the `antispam rate` value for how many messages would need to be sent before being triggered.

        Example:

        config antispam timer 4
        config antispam per 7.5
        config antispam time 30

        Requires Permission: Manage Guild

        Parameters
        -----------
        ctx: context
            The context message involved.
        rate: float
            How many seconds the rate of messages must be in before being triggered.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # Get the guild settings
            settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            settings.cd_on_message_time = rate
            session.commit()

            # Update local cache
            self.bot.guild_settings[
                ctx.message.guild.id
            ] = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            # Reinitialize all the cooldowns and their buckets
            await self.bot.antispam.set_cooldown_buckets()

            return await ctx.send(
                f"Successfully set the AntiSpam timer to: {rate} seconds."
            )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error with {ctx.command} command. {sys.exc_info()[0].__name__}: {err}"
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

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @antispam.command(aliases=["mute", "mutetime", "mutelength"])
    async def antispam_mute_time(self, ctx, *, mute_length: str):
        """Sets the antispam on_message timeout (in seconds). This is how many seconds the messages must be sent in before being triggered. Be sure to set the `antispam rate` value for how many messages would need to be sent before being triggered.

        Example:

        config antispam mute 20m
        config antispam mutetime 1h
        config antispam mutelength 1d

        Requires Permission: Manage Guild

        Parameters
        -----------
        ctx: context
            The context message involved.
        mute_length: str
            How long the user should be muted for when antispam is triggered.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # Get the guild settings
            settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            settings.antispam_mute_time = mute_length
            session.commit()

            # Update local cache
            self.bot.guild_settings[
                ctx.message.guild.id
            ] = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            return await ctx.send(
                f"Successfully set the AntiSpam Mute Time to: {mute_length}."
            )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error with {ctx.command} command. {sys.exc_info()[0].__name__}: {err}"
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

    # On Join Welcome Message Configuration
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @config.group(invoke_without_command=False)
    async def welcome(self, ctx):
        """Base for the Welcome message configuration. See `welcome msg` and `welcome enable true/false`"""
        pass

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @welcome.command(aliases=["msg", "message"])
    async def welcome_msg(self, ctx, *, text: str):
        """Sets message sent to the user upon joining the server.

        Example:

        config welcome msg text goes here that is sent to the user
        config welcome message text goes here that is sent to the user

        Requires Permission: Manage Guild

        Parameters
        -----------
        ctx: context
            The context message involved.
        text: tr
            The text that is sent to the user.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # Get the guild settings and update the channel id
            settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            settings.welcome_msg = text
            session.commit()

            # Update local cache
            self.bot.guild_settings[
                ctx.message.guild.id
            ] = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            return await ctx.send(
                f"Successfully set the On Join Welcome Message to:\n{text}"
            )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error with {ctx.command} command. {sys.exc_info()[0].__name__}: {err}"
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

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @welcome.command(aliases=["enable"])
    async def welcome_msg_enable(self, ctx, *, enabled: bool):
        """Sets whether the On Join Welcome Message feature is enabled or not.

        Example:

        config welcome enable true
        config welcome enable false

        Requires Permission: Manage Guild

        Parameters
        -----------
        ctx: context
            The context message involved.
        enabled: bool
            Whether to enable the feature.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # Get the guild settings and update the channel id
            settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            settings.welcome_msg_enabled = enabled
            session.commit()

            # Update local cache
            self.bot.guild_settings[
                ctx.message.guild.id
            ] = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            return await ctx.send(
                f"Successfully set the On Join Welcome Message feature to: {enabled}."
            )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error with {ctx.command} command. {sys.exc_info()[0].__name__}: {err}"
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

    # On Join Role Configuration
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @config.group(invoke_without_command=False)
    async def joinrole(self, ctx):
        """Base for the On Join role configuration. See `joinrole name` and `joinrole enable true/false`"""
        pass

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @joinrole.command(aliases=["name", "rolename"])
    async def joinrole_name(self, ctx, *, role_name: str):
        """Sets role to add to the user upon joining the server.

        Example:

        config joinrole name role name
        config joinrole rolename role name

        Requires Permission: Manage Guild

        Parameters
        -----------
        ctx: context
            The context message involved.
        role_name: str
            The name of the role to add to the user. This is case-insensitive.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            role = discord.utils.find(
                lambda r: r.name.lower() == role_name.lower().strip(),
                ctx.message.guild.roles,
            )

            if not role:
                return await ctx.send(f"Unable to find a role named `{role_name}`")

            # Get the guild settings and update the channel id
            settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            settings.on_join_role_id = role.id
            session.commit()

            # Update local cache
            self.bot.guild_settings[
                ctx.message.guild.id
            ] = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            return await ctx.send(
                f"Successfully set the On Join Role to: '{role.name}'"
            )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error with {ctx.command} command. {sys.exc_info()[0].__name__}: {err}"
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

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @joinrole.command(aliases=["enable"])
    async def joinrole_enable(self, ctx, *, enabled: bool):
        """Sets whether the On Join Role feature is enabled or not.

        Example:

        config joinrole enable true
        config joinrole enable false

        Requires Permission: Manage Guild

        Parameters
        -----------
        ctx: context
            The context message involved.
        enabled: bool
            Whether to enable the feature.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # Get the guild settings and update the channel id
            settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            settings.on_join_role_enabled = enabled
            session.commit()

            # Update local cache
            self.bot.guild_settings[
                ctx.message.guild.id
            ] = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            return await ctx.send(
                f"Successfully set the On Join Role feature to: {enabled}."
            )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error with {ctx.command} command. {sys.exc_info()[0].__name__}: {err}"
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

    # Activity Status Configuration
    # Bot Owner only due to all guilds it's in seeing it
    @commands.guild_only()
    @commands.is_owner()
    @config.group(aliases=["as"], invoke_without_command=False)
    async def activitystatus(self, ctx):
        """Base for the activity status (alias=as) configuration. See `activitystatus add/remove`, `activitystatus list`, `activitystatus enable true/false`"""
        pass

    @commands.guild_only()
    @commands.is_owner()
    @activitystatus.command(aliases=["add", "a"])
    async def activitystatus_add(self, ctx, *, status_text: str):
        """Adds an Activity Status that the bot displays/plays.

        Example:

        config activitystatus add status text
        config activitystatus a status text

        Requires Permission: Bot Owner

        Parameters
        -----------
        ctx: context
            The context message involved.
        status_text: str
            The text to set for the status.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            # Get current settings from the database
            guild_settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            # If the list is null/broken, start fresh
            if guild_settings.activity_status is None:
                guild_settings.activity_status = []

            current = []
            for status in guild_settings.activity_status:
                current.append(status)

            if status_text not in current:
                current.append(status_text)
                # Save to database
                guild_settings.activity_status = current
                session.commit()
                # Update local cache
                self.bot.guild_settings[
                    ctx.message.guild.id
                ] = await self.bot.helpers.get_one_guild_settings(
                    session, ctx.message.guild.id
                )

                # Send update to user
                return await ctx.send(f"Added '{status_text}' to status text rotation.")
            else:
                return await ctx.send(f"That status already exists.")

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error with {ctx.command} command. {sys.exc_info()[0].__name__}: {err}"
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

    @commands.guild_only()
    @commands.is_owner()
    @activitystatus.command(aliases=["remove", "r", "delete", "d"])
    async def activitystatus_remove(self, ctx, *, status_text: str):
        """Removes an Activity Status that the bot displays/plays.

        Example:

        config activitystatus remove status text
        config activitystatus delete status text

        Requires Permission: Bot Owner

        Parameters
        -----------
        ctx: context
            The context message involved.
        status_text: str
            The text for the status to remove.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # Get current settings stored from the database
            guild_settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            # If there is no data, don't continue
            if guild_settings.activity_status is None:
                return await ctx.send(f"You do not have any status set.")

            current = []
            for status in guild_settings.activity_status:
                current.append(status)

            # Make sure status is in the list before modifications
            if status_text in current:
                current.remove(status_text)
                # Save to the database
                guild_settings.activity_status = current
                session.commit()
                # Update local cache
                self.bot.guild_settings[
                    ctx.message.guild.id
                ] = await self.bot.helpers.get_one_guild_settings(
                    session, ctx.message.guild.id
                )

                # Send update to user
                return await ctx.send(
                    f"removed '{status_text}' from status text rotation."
                )
            else:
                await ctx.send(
                    f"That status was not found in the current list of rotation."
                )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error with {ctx.command} command. {sys.exc_info()[0].__name__}: {err}"
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

    @commands.guild_only()
    @commands.is_owner()
    @activitystatus.command(aliases=["enable"])
    async def activitystatus_enable(self, ctx, *, enabled: bool):
        """Sets whether the Activity Status feature is enabled or not.

        Example:

        config activitystatus enable true
        config activitystatus enable false

        Requires Permission: Bot Owner

        Parameters
        -----------
        ctx: context
            The context message involved.
        enabled: bool
            Whether to enable the feature.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # Get the guild settings and update the channel id
            settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )
            settings.activity_status_enabled = enabled
            session.commit()

            # Update local cache
            self.bot.guild_settings[
                ctx.message.guild.id
            ] = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            return await ctx.send(
                f"Successfully set the Activity Status to: {enabled}."
            )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error with {ctx.command} command. {sys.exc_info()[0].__name__}: {err}"
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

    @commands.guild_only()
    @commands.is_owner()
    @activitystatus.command(aliases=["list", "l"])
    async def activitystatus_list(self, ctx):
        """Lists all Activity Status that the bot displays/plays.

        Example:

        config activitystatus list
        config activitystatus l

        Requires Permission: Bot Owner

        Parameters
        -----------
        ctx: context
            The context message involved.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # Get current settings stored from the database
            guild_settings = await self.bot.helpers.get_one_guild_settings(
                session, ctx.message.guild.id
            )

            # If there are is no data, don't continue
            if guild_settings.activity_status is None:
                return await ctx.send(f"You do not have any status set.")

            embed_result_entries = []
            for status in guild_settings.activity_status:
                embed_result_entries.append(["Status:", status])

            footer_text = "Current status texts"

            p = FieldPages(ctx, per_page=8, entries=embed_result_entries,)
            p.embed.color = 0xFF8C00
            p.embed.set_author(
                name=f"Member: {ctx.message.author} ({ctx.message.author.id})",
                icon_url=ctx.message.author.avatar_url,
            )
            p.embed.set_footer(text=footer_text)
            # Send the results to the user
            return await p.paginate()

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            self.bot.log.exception(
                f"Database error with {ctx.command} command. {sys.exc_info()[0].__name__}: {err}"
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
    bot.add_cog(Config(bot))
