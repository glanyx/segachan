import sys

import discord
from discord.ext import commands


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(send_messages=True)
    @commands.guild_only()
    async def stats(self, ctx):
        """List some guild statistics.

        Requires Permission: Send Messages.
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

            guild = ctx.message.guild
            text_channels = guild.text_channels or []
            voice_channels = guild.voice_channels or []

            # In order to get a more accurate Member Count and Presence Count, we need to pull from an invite code
            member_count = int(guild.member_count)
            presence_count = 0
            # Get guild invite
            invite = await self.bot.helpers.get_guild_invite(guild)

            if invite:
                member_count = int(invite.approximate_member_count)
                presence_count = invite.approximate_presence_count

            # Create the embed
            embed = discord.Embed(
                title=f"Guild Owner: {guild.owner} ({guild.owner.id})"
            )
            embed.set_author(
                name=f"Statistics for {ctx.message.guild.name} ({ctx.message.guild.id})",
                icon_url=guild.icon_url,
            )
            # This is number of members currently in the guild
            # We're going to calculate how many max members there can be. So far the tiers are 100k, 250k, 500k
            # If we can get the value Discord provides us, use that
            if guild.max_members:
                max_members = guild.max_members
            # If less than or equal to 100,000 then use 100k
            elif member_count <= 100000:
                max_members = 100000
            # If less than or equal to 250,000 then use 250,
            elif member_count <= 250000:
                max_members = 250000
            # If less than or equal to 500,000 then use 500k
            elif member_count <= 500000:
                max_members = 500000
            # Otherwise, give it 0 to indicate that we don't know
            else:
                max_members = 0

            embed.add_field(
                name="Member Count",
                value=f"{member_count:,} / {max_members:,}",
                inline=True,
            )
            # This is maximum number of presence members, or people currently connected to the guild
            max_presences = guild.max_presences if guild.max_presences else 5000
            embed.add_field(
                name="Presence Count",
                value=f"{presence_count:,} / {max_presences:,}",
                inline=True,
            )
            # Number of text channels
            embed.add_field(
                name="Text Channels", value=f"{len(text_channels)}", inline=True
            )
            # Number of voice users
            embed.add_field(
                name="Active Voice Users",
                value=f"{sum(len(vc.members or []) for vc in voice_channels)}",
                inline=True,
            )
            # Number of voice channels
            embed.add_field(
                name="Active Voice Channels",
                value=f"{len(list(filter(lambda vc: len(vc.members) > 0, voice_channels)))} / {len(voice_channels)}",
                inline=True,
            )
            # Number of boosters
            embed.add_field(
                name="Boosters",
                value=f"{guild.premium_subscription_count}",
                inline=True,
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
    bot.add_cog(Stats(bot))
