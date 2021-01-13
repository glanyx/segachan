import sys
from datetime import datetime

import discord
from discord.ext import commands
from sqlalchemy.exc import DBAPIError

from sweeperbot.cogs.utils.paginator import FieldPages
from sweeperbot.db import models

class ListRequests(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["list"])
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def listrequests(self, ctx):
        """Gets a list of existing port requests.

        Requires Permission: Manage Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        """

        session = self.bot.helpers.get_db_session()

        try:
            self.bot.log.info(
                f"CMD {ctx.invoked_with} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            
            guild = ctx.message.guild
            settings = self.bot.guild_settings.get(guild.id)

            request_channel = settings.request_channel
            downvotes_allowed = settings.allow_downvotes
            questions_allowed = settings.allow_questions
            
            guild_requests = (
                session.query(models.Requests)
                .join(models.Server, models.Server.id == models.Requests.server_id)
                .filter(models.Server.discord_id == ctx.message.guild.id)
                .filter(models.Requests.status == models.RequestStatus.open)
                .order_by(models.Requests.upvotes.desc())
                .order_by(models.Requests.downvotes.asc())
                .order_by(models.Requests.text.asc())
                .all()
            )

            embed_array = []
            counter = 0

            embed = discord.Embed(
                color=0x14738E,
                title="List of Requests",
                timestamp=datetime.utcnow()
            )

            # Loop through existing requests
            for singleRequest in guild_requests:

                game_title = getattr(singleRequest, "text")
                upvotes = getattr(singleRequest, "upvotes")
                downvotes = getattr(singleRequest, "downvotes")
                questions = getattr(singleRequest, "questions")
                message_id = getattr(singleRequest, "message_id")
                
                link = f"https://discord.com/channels/{ctx.guild.id}/{request_channel}/{message_id}"
                content_length = len(game_title) + len(str(upvotes)) + len(str(downvotes)) + len(str(questions)) + len(link) + 100

                if len(embed) + content_length > 6000:
                    embed_array.append(embed)
                    embed = discord.Embed(
                        color=0x14738E,
                        title="List of Requests (cont.)",
                        timestamp=datetime.utcnow()
                    )

                field_string = f"Upvotes: *{upvotes}*"
                field_string += f"\nDownvotes: *{downvotes}*" if downvotes_allowed else ""
                field_string += f"\nQuestions: *{questions}*" if questions_allowed else ""

                embed.add_field(
                  name=game_title,
                  value=f"{field_string}\n[Link]({link})",
                  inline=False
                )
                
            embed_array.append(embed)

            for embed_chunk in embed_array:
                await ctx.send(embed=embed_chunk)

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
    bot.add_cog(ListRequests(bot))
