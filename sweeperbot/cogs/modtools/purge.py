import sys
import typing
from datetime import datetime, timedelta

import discord
from discord.ext import commands


class Purge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["clear"])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    @commands.guild_only()
    async def purge(
        self, ctx, number_of_messages: int, user_id: typing.Optional[int] = None
    ):
        """Purges up to the specified number of messages in current channel.

        If a user id is provided it will only purge their messages, up to a max of 100 within the last 2 weeks.

        Requires Permission: Manage Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        number_of_messages: Optional[str]
            Maximum number of messages the bot should remove.
        user_id: Optional[str]
            The Discord ID the messages should be purged for.
        """

        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            deleted = None
            # Increase count by 1 to account for the calling command
            number_of_messages += 1
            # If we were provided an ID, let's try and use it
            if user_id:
                member = await self.bot.helpers.get_member_or_user(
                    user_id, ctx.message.guild
                )
                if not member:
                    return await ctx.send(
                        f"Unable to find the requested user. Please make sure the user ID or @ mention is valid."
                    )
                message_delete_list = []
                # We're going to search for the number of messages the user wants to delete, plus a few hundred more
                # in case they are mixed within other messages
                count = 0
                # Set 2 weeks from now as max search period
                after_date = datetime.utcnow() - timedelta(days=13)
                # limited to current channel due to Discord limitation
                # TO DO - Hook into the Database and pull message ID's then create a message snowflake to delete
                async for message in ctx.message.channel.history(
                    limit=number_of_messages + 200, after=after_date
                ):
                    if message.author.id == member.id:
                        # Since we only want up to the number_of_messages for that user, if we hit that, break out
                        if count == 100 or count == number_of_messages:
                            break
                        else:
                            count += 1
                            message_delete_list.append(message)
                            # print(f"[{message.created_at}] {message.author}: {message.content}"[:1950])
                # If messages found, delete using the Bulk Delete method
                if message_delete_list:
                    try:
                        await ctx.message.channel.delete_messages(message_delete_list)
                        deleted = message_delete_list
                    except discord.HTTPException as err:
                        return await ctx.send(f"Error processing {ctx.command}: {err}")

            else:
                # Uses multiple strategies for deleting all messages up to the limit specified, which can be a bulk
                # delete or individually deleting
                deleted = await ctx.message.channel.purge(limit=number_of_messages)

            if deleted:
                emoji = self.bot.get_emoji(
                    self.bot.constants.reactions["animated_sweeperbot"]
                )
                await ctx.send(f"{emoji} Successfully purged {len(deleted)} messages.")
            else:
                await ctx.send(f"No messages matched the query, 0 messages deleted.")
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
    bot.add_cog(Purge(bot))
