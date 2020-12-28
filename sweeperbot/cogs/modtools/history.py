import sys

import discord
from discord.ext import commands
from sqlalchemy.exc import DBAPIError

from sweeperbot.cogs.utils.paginator import FieldPages


class History(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["h"])
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def history(self, ctx, user_id: str):
        """Gets users history record.

        Example:

        history userID
        h @wumpus#0000

        Requires Permission: Manage Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_id: str
            The user/member the history is for.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            guild = ctx.message.guild
            user = await self.bot.helpers.get_member_or_user(user_id, guild)
            if not user:
                return await ctx.send(
                    f"Unable to find the requested user. Please make sure the user ID or @ mention is valid."
                )

            (
                embed_result_entries,
                footer_text,
            ) = await self.bot.helpers.get_action_history(session, user, guild)

            p = FieldPages(ctx, per_page=8, entries=embed_result_entries,)
            p.embed.color = 0xFF8C00
            p.embed.set_author(
                name=f"Member: {user} ({user.id})", icon_url=user.avatar_url
            )
            p.embed.set_footer(text=footer_text)
            await p.paginate()
        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except DBAPIError as err:
            self.bot.log.exception(
                f"Error logging note to database. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
            session.rollback()
        except Exception as err:
            self.bot.log.exception(
                f"Error responding to {ctx.command} via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        finally:
            session.close()


def setup(bot):
    bot.add_cog(History(bot))
