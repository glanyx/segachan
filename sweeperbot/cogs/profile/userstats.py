import sys
import typing
from datetime import datetime

import discord
from discord.ext import commands

from sweeperbot.utilities.helpers import set_sentry_scope


class UserStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["us", "user"])
    @commands.guild_only()
    async def userstats(self, ctx, *, user_id: typing.Optional[str] = None):
        """Creates info about the user.

        Requires Permission: Send Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_id: Optional[str]
            The Discord ID the user stats should be retrieved for.
        modmail_bypass: Optional[bool]
            Whether the request is being used for modmail server and role mentions should be text.
        """
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

            member = None
            modmail_bypass = False
            # If we were provided an ID, let's try and use it
            if user_id:
                member = await self.bot.helpers.get_member_or_user(
                    user_id, ctx.message.guild
                )
                if not member:
                    return await ctx.send(
                        f"Unable to find the requested user. Please make sure the user ID or @ mention is valid."
                    )

            # If no user ID then pull user stats from the command caller
            if not member:
                member = ctx.message.author

            embed = discord.Embed(color=0xFF8C00, timestamp=datetime.utcnow())
            embed.set_author(name=f"{member} ({member.id})", icon_url=member.avatar_url)

            # If it's a User meaning we get limited info
            if isinstance(member, discord.User):
                # Discord join date
                discord_join_date = self.bot.helpers.relative_time(
                    datetime.utcnow(), member.created_at, brief=True
                )
                discord_join_date = f"{member.created_at.replace(microsecond=0)}\n*{discord_join_date} ago*"
                embed.add_field(name="Joined Discord", value=f"{discord_join_date}")
            # If it's a Member meaning we get guild specific and detailed info
            elif isinstance(member, discord.Member):
                # If they have an activity status (Playing, Watching, Custom), add that
                tmp_activities = []
                for activity in member.activities:
                    if activity.type == discord.ActivityType.custom:
                        tmp_activities.append(
                            f"**{self.bot.constants.activity_enum[activity.type]}:** {activity}"
                        )
                    elif activity.type == discord.ActivityType.playing:
                        tmp_activities.append(
                            f"**{self.bot.constants.activity_enum[activity.type]}:** {activity.name}"
                        )
                    else:
                        tmp_activities.append(
                            f"**{self.bot.constants.activity_enum[activity.type]}:** {activity.name}"
                        )

                activities = "\n".join(tmp_activities)
                embed.description = f"**__Activities__**\n{activities}"
                # If they are in a Voice Channel, add that
                if member.voice and member.voice.channel:
                    voice_info = f"**Name:** {member.voice.channel.name}"
                    embed.description = (
                        f"{embed.description}\n\n**__Voice Channel__**\n{voice_info}"
                    )
                # Nickname
                embed.title = f"Nickname: {member.nick}"
                # User Status
                discord_status = str(member.status)
                embed.add_field(
                    name="User Status",
                    value=f"{self.bot.constants.statuses[discord_status]} {self.bot.constants.statuses['mobile'] if member.is_on_mobile() else ''}\n{member.mention}",
                )
                # Guild join date
                guild_join_date = self.bot.helpers.relative_time(
                    datetime.utcnow(), member.joined_at, brief=True
                )
                guild_join_date = f"{member.joined_at.replace(microsecond=0)} UTC\n*{guild_join_date} ago*"
                embed.add_field(name="Joined Guild", value=f"{guild_join_date}")

                # Discord join date
                discord_join_date = self.bot.helpers.relative_time(
                    datetime.utcnow(), member.created_at, brief=True
                )
                discord_join_date = f"{member.created_at.replace(microsecond=0)} UTC\n*{discord_join_date} ago*"
                embed.add_field(name="Joined Discord", value=f"{discord_join_date}")

                # Roles
                roles = list(reversed(member.roles))
                roles_temp = []
                if modmail_bypass:
                    for role in roles:
                        roles_temp.append(role.name)
                else:
                    for role in roles:
                        roles_temp.append(role.mention)

                # little logic to split into embeds with 1000 characters max
                out = ""
                for line in roles_temp:
                    out += ", " + line
                    if len(out) > 950:
                        embed.add_field(name="Roles", value=out.lstrip(", "))
                        out = ""

                if len(out) != 0:
                    embed.add_field(name="Roles", value=out.lstrip(", "))

            await ctx.send(embed=embed)

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
    bot.add_cog(UserStats(bot))
