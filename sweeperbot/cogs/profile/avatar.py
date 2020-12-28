import io
import sys
import typing

import aiohttp
import discord
from discord.ext import commands


class Avatar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["avi", "pfp"])
    @commands.has_permissions(send_messages=True)
    @commands.bot_has_permissions(attach_files=True, send_messages=True)
    @commands.guild_only()
    async def avatar(self, ctx, user_id: typing.Optional[str] = ""):
        """Shows the profile picture of the requested user.

        Example:

        pfp userID
        avi @wumpus#0000

        Requires Permission: Send Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_id: Optional[str]
            The user/member the notes are related to. Can be an ID or a mention. If none provides it shows your avatar.
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

            user = None
            # If a user is provided, then get their profile
            if user_id:
                user = await self.bot.helpers.get_member_or_user(
                    user_id, ctx.message.guild
                )
                if not user:
                    return await ctx.send(
                        f"Unable to find the requested user. Please make sure the user ID or @ mention is valid."
                    )
            # If no user ID then pull user info from the command caller
            if not user:
                user = ctx.message.author
            # Sets the proper file extension
            if user.is_avatar_animated():
                avatar_ext = "gif"
            else:
                avatar_ext = "png"
            # Downloads and then sends the file on Discord
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{user.avatar_url}") as resp:
                    if resp.status != 200:
                        return await ctx.send("Error downloading that users avatar.")
                    data = io.BytesIO(await resp.read())
                    await ctx.send(
                        file=discord.File(data, f"pfp_uid_{user.id}.{avatar_ext}")
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
    bot.add_cog(Avatar(bot))
