import sys

import discord
from discord.ext import commands


class Send(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["s"])
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def send(self, ctx, user_id: str, *, message_text: str):
        """Allows you to send text to a user via the bot.

        Example:

        send userID this is a test message
        s @wumpus#0000 this is a test message

        Requires Permission: Manage Guild

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_id: str
            The user/member the action is related to. Can be an ID or a mention
        message_text: str
            The text you want to send to the user."""

        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            # Get the user profile
            user = await self.bot.helpers.get_member_or_user(user_id, ctx.message.guild)
            if not user:
                return await ctx.send(
                    f"Unable to find the requested user. Please make sure the user ID or @ mention is valid."
                )
            # Don't allow you to send to bots as it won't work
            if user.bot:
                return await ctx.send(
                    f"Sorry, but you are not allowed to send to that user."
                )
            # Set some meta data
            action_type = "Message"
            guild = ctx.message.guild
            settings = self.bot.guild_settings.get(guild.id)
            modmail_enabled = settings.modmail_server_id

            # Format the message
            message = self.bot.constants.infraction_header.format(
                action_type=action_type.lower(), guild=guild
            )

            # Reduces the text to 1,800 characters to leave enough buffer for header and footer text
            message += f"{message_text[:1800]}"
            # Set footer based on if the server has modmail or not
            if modmail_enabled:
                message += self.bot.constants.footer_with_modmail.format(guild=guild)
            else:
                message += self.bot.constants.footer_no_modmail.format(guild=guild)
            try:
                reply = await user.send(message)
                if reply:
                    await ctx.send(
                        f"Successfully sent that message to {user} ({user.id})"
                    )
            except discord.Forbidden:
                await ctx.send(
                    f"Unable to send the message to {user} ({user.id}). User may have blocked the bot or the bot no longer shares any servers with them."
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
    bot.add_cog(Send(bot))
