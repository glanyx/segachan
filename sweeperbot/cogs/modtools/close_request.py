import asyncio
import sys
from datetime import datetime

import discord
from discord.ext import commands
from sqlalchemy.exc import DBAPIError

from sweeperbot.db import models

class CloseRequest(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @commands.command(aliases=["crq"])
    async def closerequest(self, ctx, message_id):
        """Closes the specified Request.

        Requires Permission: Manage Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        message_id: str
            The message id of the request.
        """

        if not message_id:
            ctx.send("Please enter a Message ID as the argument for this command.")
            return

        session = self.bot.helpers.get_db_session()

        try:
            guild = ctx.message.guild
            settings = self.bot.guild_settings.get(guild.id)
            request_channel = settings.request_channel

            if request_channel is None:
                  return await ctx.send(
                    f"No requests channel found. Please set one on the configuration."
                )

            channel = guild.get_channel(request_channel)
            
            found_request = (
                session.query(models.Requests)
                .join(models.Server, models.Server.id == models.Requests.server_id)
                .filter(models.Server.discord_id == guild.id)
                .filter(models.Requests.message_id == message_id)
                .first()
            )

            if not found_request:
                await ctx.send("Unable to find a Request by the specified Message ID.")
                return

            found_request.status = models.RequestStatus.closed
            session.add(found_request)
            session.commit()

            message = await channel.fetch_message(message_id)
            await message.delete()

            await ctx.message.delete()
            await ctx.send(f"Successfully closed the request for `{found_request.text}`!")

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except DBAPIError as err:
            self.bot.log.exception(
                f"Error closing request for Message ID: ({message_id}). {sys.exc_info()[0].__name__}: {err}"
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
    bot.add_cog(CloseRequest(bot))
