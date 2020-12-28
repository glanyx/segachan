import sys

import discord
from discord.ext import commands


class Vote(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.bot_has_permissions(external_emojis=True, add_reactions=True)
    @commands.guild_only()
    async def vote(self, ctx):
        """Adds voting reactions on the message made. Includes an upvote, downvote, and blank."""
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

            # Get the reactions
            upvote = self.bot.get_emoji(self.bot.constants.reactions["upvote"])
            downvote = self.bot.get_emoji(self.bot.constants.reactions["downvote"])
            spacer = self.bot.get_emoji(self.bot.constants.reactions["spacer"])

            # Add the reactions
            for emoji in (upvote, downvote, spacer):
                if emoji:
                    await ctx.message.add_reaction(emoji)

        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error responding to {ctx.invoked_with} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
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
    bot.add_cog(Vote(bot))
