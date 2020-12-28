import sys

import discord
from discord.ext import commands


class Ping(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(send_messages=True)
    @commands.guild_only()
    @commands.cooldown(3, 60, commands.BucketType.user)
    async def ping(self, ctx):
        """Shows bot API and Response latency and confirms bot is running.

        Requires Permission: Send Messages
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
            msg = await ctx.send(f"Pong! 🏓")
            msg_diff = round(
                (msg.created_at - ctx.message.created_at).total_seconds() * 1000
            )
            api_latency = round(self.bot.latency * 1000)
            await msg.edit(
                content=f"Pong! 🏓\n\n**API Latency:** {api_latency}ms\n**Response Latency:** {msg_diff}ms"
            )
        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error responding to {ctx.command} via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
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
    bot.add_cog(Ping(bot))
