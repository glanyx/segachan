import sys

import discord
from discord.ext import commands


class ShowDM(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["getdm"])
    @commands.is_owner()
    @commands.guild_only()
    async def showdm(self, ctx, user_id: int):
        """Gets the DM history between the Bot and the User. Owner Only.

        Usage:
        getdm userid
        showdm 123456789123456789
        """
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            user = ctx.bot.get_user(user_id)
            if not user:
                self.bot.log.debug(
                    f"ShowDM: User {user_id} not found via get_user, trying fetch"
                )
                user = await ctx.bot.fetch_user(user_id)
                if not user:
                    self.bot.log.debug(
                        f"ShowDM: User {user_id} not found via fetch, exiting"
                    )
                    return await ctx.send(f"User {user_id} not found, exiting")

            channel = user.dm_channel
            if not channel:
                self.bot.log.debug(
                    f"ShowDM: dm_channel not found for {user_id}, creating one"
                )
                channel = await user.create_dm()
                if not channel:
                    self.bot.log.debug(
                        f"ShowDM: Unable to create dm channel for {user_id}, exiting"
                    )
                    return ctx.send(
                        f"Unable to create dm channel for {user_id}, exiting"
                    )

            messages = await channel.history(limit=13).flatten()
            for msg in messages:
                await ctx.send(
                    f"```css\n[{msg.created_at}] {msg.author} ({msg.author.id}): {msg.content[:1850]}```"
                )

        except discord.HTTPException as err:
            self.bot.log.error(
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
    bot.add_cog(ShowDM(bot))
