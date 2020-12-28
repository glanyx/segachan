import sys

import discord
from discord.ext import commands


class Server(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(send_messages=True)
    @commands.guild_only()
    async def server(self, ctx, guild_invite: str):
        """Looks up a guild based on Invite Link and returns info about it.

        Requires Permission: Send Messages.

        Parameters
        -----------
        ctx: context
            The context message involved.
        guild_invite: str
            A Discord Invite link to fetch the info for.
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

            try:
                invite = await ctx.bot.fetch_invite(guild_invite, with_counts=True)
            except discord.errors.NotFound:
                return await ctx.send(
                    f"Sorry, I was unable to find any guild from that invite. Please make sure the invite code is valid."
                )

            guild = invite.guild
            member_count = invite.approximate_member_count
            presence_count = invite.approximate_presence_count

            # Create the embed
            embed = discord.Embed(description=f"> {guild.description}")
            embed.set_author(
                name=f"Info for: {guild.name} ({guild.id})", icon_url=guild.icon_url,
            )
            # This is an approx number of members currently in the guild
            embed.add_field(
                name="Member Count", value=f"{member_count:,}", inline=True,
            )
            # This is an approx number of presence members, or people currently connected to the guild
            embed.add_field(
                name="Presence Count", value=f"{presence_count:,}", inline=True,
            )
            # Guild creation date
            embed.add_field(
                name="Guild Creation",
                value=f"{guild.created_at.replace(microsecond=0)} UTC",
                inline=True,
            )
            # Guild features
            features = guild.features if guild.features else "None"
            embed.add_field(name="Features", value=f"{features}", inline=False)
            # Verification Level
            embed.add_field(
                name="Verification Level",
                value=f"{guild.verification_level}",
                inline=False,
            )
            embed.set_thumbnail(url=guild.icon_url)
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
    bot.add_cog(Server(bot))
