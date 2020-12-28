import sys

import discord
from discord.ext import commands


class Shutdown(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def shutdown(self, ctx):
        """Initiates bot termination gracefully.

        Requires Permission: Bot Owner
        """
        try:
            self.bot.log.warning(
                f"CMD {ctx.invoked_with} called by {ctx.author} ({ctx.message.author.id})"
            )
            confirm = await self.bot.prompt.send(
                ctx, "Are you sure you want to do shutdown the bot?"
            )
            if confirm:
                await ctx.send("Confirmation received. Shutting down.")
                await self.bot.close()
            elif confirm is False:
                return await ctx.send("Cancelling shutdown.")
            elif confirm is None:
                return await ctx.send("Shutdown prompt timed out.")
        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error responding to {ctx.invoked_with} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )


def setup(bot):
    bot.add_cog(Shutdown(bot))
