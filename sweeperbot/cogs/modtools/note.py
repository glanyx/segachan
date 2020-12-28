import sys
from datetime import datetime

import discord
from discord.ext import commands
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import literal_column

from sweeperbot.db import models


class Note(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @commands.group(aliases=["n"], invoke_without_command=True)
    async def note(self, ctx):
        """Provides note commands for a user such as add, edit, delete.

        Requires Permission: Manage Messages
        """
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            await ctx.send(
                "This is the base note command. Use `note add`, `note delete`, or `note edit` or `note view` for further functionality."
            )
        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.invoked_with} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except Exception as err:
            self.bot.log.exception(
                f"Error responding to {ctx.invoked_with} via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )

    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @note.command(aliases=["a", "A"])
    async def add(self, ctx, user_id: str, *, note_text: str):
        """Adds a note to a users record.

        Example:

        note add userID this is a test note
        note add @wumpus#0000 this is a test note

        Requires Permission: Manage Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_id: str
            The user/member the notes are related to. Can be an ID or a mention
        note_text: str
            The note text you are adding to the record.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )
            user = await self.bot.helpers.get_member_or_user(user_id, ctx.message.guild)
            if not user:
                return await ctx.send(
                    f"Unable to find the requested user. Please make sure the user ID or @ mention is valid."
                )

            # Get mod's DB profile
            db_mod = await self.bot.helpers.db_get_user(session, ctx.message.author.id)
            # Get the DB profile for the guild
            db_guild = await self.bot.helpers.db_get_guild(
                session, ctx.message.guild.id
            )
            # Get the DB profile for the user
            db_user = await self.bot.helpers.db_get_user(session, user.id)

            logged_action = models.Action(mod=db_mod, server=db_guild)
            new_note = models.Note(
                text=note_text, user=db_user, server=db_guild, action=logged_action
            )
            session.add(new_note)
            session.commit()

            await ctx.send(
                f"Successfully stored note #{new_note.id} for: {user} ({user.id})"
            )
        except discord.HTTPException as err:
            self.bot.log.error(
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
                f"Unable to log note due to database error for: ({user_id}). Error has already been reported to my developers."
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

    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @note.command(aliases=["e", "E"])
    async def edit(self, ctx, user_id: str, note_id: str, *, note_text: str):
        """Edits a note on a users record.

        Example:

        note edit userID noteID new note message
        note add @wumpus#0000 new note message

        Requires Permission: Manage Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_id: str
            The user/member the note is related to.
        note_id: str
            The note id to edit.
        note_text: str
            The note text you are updating on the record.
        """

        session = self.bot.helpers.get_db_session()
        try:
            user = await self.bot.helpers.get_member_or_user(user_id, ctx.message.guild)
            if not user:
                return await ctx.send(
                    f"Unable to find the requested user. Please make sure the user ID or @ mention is valid."
                )

            # Clean the Note ID since some people put the #numb when it should just be int
            try:
                note_id = int(note_id.replace("#", ""))
            except ValueError:
                return await ctx.send(
                    f"You must provide the Note ID that you want to edit."
                )

            # Get mod's DB profile
            db_mod = await self.bot.helpers.db_get_user(session, ctx.message.author.id)
            # Get the DB profile for the guild
            db_guild = await self.bot.helpers.db_get_guild(
                session, ctx.message.guild.id
            )
            # Get the DB profile for the user
            db_user = await self.bot.helpers.db_get_user(session, user.id)

            # Get the note by the ID
            logged_note = session.query(models.Note).get(note_id)
            # Now let's make sure the user isn't trying to update a note they aren't authorized for
            if logged_note and (
                logged_note.server_id == db_guild.id
                and logged_note.user_id == db_user.id
            ):
                new_action = models.Action(mod=db_mod, server=db_guild)
                session.add(new_action)
                session.commit()

                logged_note.text = note_text
                logged_note.action_id = new_action.id
                session.add(logged_note)
                session.commit()

                await ctx.send(
                    f"Successfully updated note #{logged_note.id} for: {user} ({user.id})"
                )
            else:
                await ctx.send(
                    f"Unable to update that note. Please make sure you are providing a valid note ID and user ID."
                )
        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except DBAPIError as err:
            self.bot.log.exception(
                f"Error saving edited note for: ({user_id}). {sys.exc_info()[0].__name__}: {err}"
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

    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @note.command(aliases=["d", "D", "r", "R", "remove"])
    async def delete(self, ctx, user_id: str, note_id: str):
        """Deletes the specific note from a users record.

        Example:

        note delete userID noteID
        note delete @wumpus#0000 noteID

        Requires Permission: Manage Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_id: str
            The user/member the notes are related to.
        note_id: str
            The note you are deleting.
        """

        session = self.bot.helpers.get_db_session()
        try:
            user = await self.bot.helpers.get_member_or_user(user_id, ctx.message.guild)
            if not user:
                return await ctx.send(
                    f"Unable to find the requested user. Please make sure the user ID or @ mention is valid."
                )

            # Clean the Note ID since some people put the #numb when it should just be numb
            note_id = int(note_id.replace("#", ""))

            # Get the DB profile for the guild
            db_guild = await self.bot.helpers.db_get_guild(
                session, ctx.message.guild.id
            )
            # Get the DB profile for the user
            db_user = await self.bot.helpers.db_get_user(session, user.id)

            # Get the note by the ID
            logged_note = session.query(models.Note).get(note_id)
            # Now let's make sure the user isn't trying to update a note they aren't authorized for
            if logged_note and (
                logged_note.server_id == db_guild.id
                and logged_note.user_id == db_user.id
            ):

                confirm = await self.bot.prompt.send(
                    ctx, "Are you sure you want to delete the note?"
                )
                if confirm:
                    session.delete(logged_note)
                    session.commit()
                    await ctx.send(f"Successfully deleted note for: {user} ({user.id})")
                elif confirm is False:
                    return await ctx.send("Cancelling request.")
                elif confirm is None:
                    return await ctx.send("Request timed out.")
            else:
                await ctx.send(
                    f"Unable to delete that note. Please make sure you are providing a valid note ID and user ID."
                )
        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except DBAPIError as err:
            self.bot.log.exception(
                f"Error deleting note for: ({user_id}). {sys.exc_info()[0].__name__}: {err}"
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

    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @note.command(aliases=["v", "V"])
    async def view(self, ctx, user_id: str, note_id: str):
        """Views a specific note from a users record.

        Example:

        note view userID noteID
        note view @wumpus#0000 noteID

        Requires Permission: Manage Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_id: str
            The user/member the note is related to.
        note_id: str
            The note id to view.
        """

        session = self.bot.helpers.get_db_session()
        try:
            user = await self.bot.helpers.get_member_or_user(user_id, ctx.message.guild)
            if not user:
                return await ctx.send(
                    f"Unable to find the requested user. Please make sure the user ID or @ mention is valid."
                )

            # Clean the Note ID since some people put the #numb when it should just be numb
            note_id = int(note_id.replace("#", ""))
            # Creates an alias to the User table specifically to be used for the user.
            # Otherwise using models.User.discord_id == user.id will match against the Mod
            # due to prior join to the User table
            user_alias = aliased(models.User)

            # Get the note by the ID
            note_query = (
                session.query(
                    models.Note.id,
                    models.Note.created.label("created"),
                    models.Note.text,
                    models.User,
                    literal_column("'Note'").label("type"),
                    models.Note.created.label("expires"),
                )
                # Links the Note and Action table (used for next 2 joins)
                .join(models.Action, models.Action.id == models.Note.action_id)
                # Links the User and Action table to get the Mod
                .join(models.User, models.User.id == models.Action.mod_id)
                # Links the Server and Note table to get the Guild
                .join(models.Server, models.Server.id == models.Note.server_id)
                # Links the User and Note table to get the User
                .join(user_alias, user_alias.id == models.Note.user_id)
                # Filters on the user alias where the users Discord ID matches
                # And where the guilds Discord ID matches
                .filter(
                    user_alias.discord_id == user.id,
                    models.Server.discord_id == ctx.message.guild.id,
                    models.Note.id == note_id,
                )
            )
            for result in note_query:
                # Format the data
                action_dbid = result[0]
                action_date = result[1]
                action_date_friendly = (
                    action_date.strftime("%b %d, %Y %I:%M %p") + " UTC"
                )
                action_text = result[2]
                action_mod = result[3]
                action_type = result[4]

                # Take the results and create the embed
                embed = discord.Embed(color=0xFF8C00, timestamp=datetime.utcnow())
                embed.set_author(
                    name=f"Member: {user} ({user.id})", icon_url=user.avatar_url
                )
                embed.description = action_text
                data_title = (
                    f"{action_type} - {action_date_friendly} | *#{action_dbid}*"
                )
                data_value = f"Mod: <@{action_mod.discord_id}>"

                embed.add_field(name=data_title, value=data_value, inline=False)

                await ctx.send(embed=embed)

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except DBAPIError as err:
            self.bot.log.exception(
                f"Error saving edited note for: ({user_id}). {sys.exc_info()[0].__name__}: {err}"
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
    bot.add_cog(Note(bot))
