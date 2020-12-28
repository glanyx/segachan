import os
import sys
from datetime import datetime

import discord
import psutil
from discord.ext import commands


class Info(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["invite"])
    @commands.has_permissions(send_messages=True)
    @commands.guild_only()
    async def info(self, ctx):
        """Provides information about the bot including an invite link, source code,
        memory and cpu usage, etc.

        Requires Permission
        -------------------
        Send Messages
        """
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

            # Get bot uptime
            uptime = self.bot.helpers.relative_time(
                datetime.utcnow(), self.bot.started_time, brief=True
            )

            # Get system usage
            process = psutil.Process(os.getpid())
            cpu_usage = process.cpu_percent() / psutil.cpu_count()
            try:
                memory_usage = process.memory_full_info().uss / 1024 ** 2
            except psutil.AccessDenied:
                memory_usage = 0.00

            # Create the embed of info
            embed = discord.Embed(
                color=discord.Color.blurple(),
                title="Bot Invite Link & Info",
                timestamp=datetime.utcnow(),
            )
            # Gets the bot owner info.
            if isinstance(self.bot.owner, list):
                owners = [
                    f"{temp_user.mention} ({temp_user.id})"
                    for temp_user in self.bot.owner
                ]
            else:
                owners = [f"{self.bot.owner.mention} ({self.bot.owner.id})"]
            owners_string = ", ".join(owners)
            embed.add_field(name="Bot Owner", value=f"{owners_string}", inline=False)

            # Generate Invite Permissions Link
            perms = discord.Permissions.none()
            perms.administrator = False  # Never needed
            perms.view_audit_log = (
                True  # Used for watching ban/kick events done outside the bot
            )
            # perms.view_guild_insights = False
            perms.manage_guild = True  # Used for getting list of guild invites
            perms.manage_roles = True  # For adding/removing roles during mutes
            perms.manage_channels = (
                True  # Related to antispam functions for locking down during raids
            )
            perms.kick_members = True  # To use the kick users command
            perms.ban_members = True  # To use the ban users command
            perms.create_instant_invite = True  # To allow more accurate server stats
            perms.change_nickname = False
            perms.manage_nicknames = (
                True  # Future functionality for changing bad actors names
            )
            perms.manage_emojis = False
            perms.manage_webhooks = False
            perms.read_messages = True  # To view server messages
            perms.send_messages = True  # To send messages
            perms.send_tts_messages = False
            perms.manage_messages = (
                True  # To remove messages such as anti spam blacklisted items
            )
            perms.embed_links = (
                True  # Bot uses embeds for fancy displaying of information
            )
            perms.attach_files = (
                True  # Used in various areas such as the pfp/avatar command
            )
            perms.read_message_history = True  # To view previous messages
            perms.mention_everyone = False
            perms.external_emojis = (
                True  # To use emojis from the bot server for various functionality
            )
            perms.add_reactions = (
                True  # Used for commands like vote, confirmation on commands
            )
            perms.connect = False
            perms.speak = False
            perms.mute_members = False
            perms.deafen_members = False
            perms.move_members = True  # Used to disconnect users from voice when muted
            perms.use_voice_activation = False
            perms.priority_speaker = False

            embed.add_field(
                name="Invite Link",
                value=f"[Click here.]({discord.utils.oauth_url(self.bot.user.id, perms)})",
                inline=True,
            )
            embed.add_field(
                name="Source Code",
                value=f"[Click here.]({self.bot.constants.repository_link})",
                inline=True,
            )
            embed.add_field(
                name="Support Server",
                value=f"[Click here.]({self.bot.constants.support_invite_link})",
                inline=True,
            )
            embed.add_field(
                name="Bot Version", value=f"{self.bot.version}", inline=True
            )
            embed.add_field(
                name="# of Guilds", value=f"{len(self.bot.guilds)}", inline=True
            )
            embed.add_field(
                name="Memory Usage", value=f"{memory_usage:.2f} MiB", inline=True
            )
            embed.add_field(name="CPU Usage", value=f"{cpu_usage:.2f}%", inline=True)
            embed.add_field(name="Bot Uptime", value=f"{uptime}", inline=True)
            embed.add_field(
                name="Donation Link",
                value=f"Appreciate the project and want to donate? [Please click here.]({self.bot.constants.patreon_link})",
                inline=False,
            )

            await ctx.send(embed=embed)
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
    bot.add_cog(Info(bot))
