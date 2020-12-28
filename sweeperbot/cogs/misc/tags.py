import re
import sys

import discord
from discord.ext import commands
from sqlalchemy import exc, desc

from sweeperbot.cogs.utils.paginator import FieldPages
from sweeperbot.db import models
from sweeperbot.utilities.helpers import has_guild_permissions, set_sentry_scope


class Tags(commands.Cog):
    """The tag related commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.guild_only()
    @has_guild_permissions(send_messages=True)
    @commands.group(aliases=["t", "tags"], invoke_without_command=True)
    @commands.cooldown(3, 90, commands.BucketType.user)
    async def tag(self, ctx, *, tag_name: str):
        """Gets a specific tag. Tag names are case-insensitive.

        Tags allow moderators to create call-response messages, similar to commands on the fly for their guilds.

        Example:

        tag tagname

        Requires Permission: Send Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        tag_name: str
            The name of the tag to get.
        """

        session = self.bot.helpers.get_db_session()
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
            # Get the tag where tag name and guild ID match
            tag = (
                session.query(models.Tags)
                # Links the Server and Note table to get the Guild
                .join(models.Server, models.Server.id == models.Tags.server_id)
                .filter(
                    models.Server.discord_id == ctx.message.guild.id,
                    models.Tags.name == tag_name.strip(),
                )
                .first()
            )
            if not tag:
                return await ctx.send(
                    f"Sorry, unable to find a tag named **{tag_name}**."
                )

            # Send the tag contents
            await ctx.send(tag.content)
            # Update use counter. It's important to call the models column to increment vs using:
            # tag.uses += 1 as this will use python to increment the counter and create race conditions
            tag.uses = models.Tags.uses + 1
            session.commit()
        except discord.HTTPException as err:
            set_sentry_scope(ctx)
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Database error retrieving tag '{tag_name}'. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
            session.rollback()
        except Exception as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Error responding to {ctx.command} for tag '{tag_name}'. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        finally:
            session.close()

    @commands.guild_only()
    @has_guild_permissions(manage_messages=True)
    @tag.command(aliases=["add", "a", "A"])
    async def create(self, ctx, tag_name: str, *, tag_content: commands.clean_content):
        """Creates a new tag for the guild. Everything after the tag name is used as the tag content. Everyone, here and role mentions are escaped to prevent abuse.

        Example:

        tag create tagname this is a test tag
        with a new line **and bold formatting**

        Requires Permission: Manage Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        tag_name: str
            The name of the tag to create.
        tag_content: str
            The content for the new tag.
        """

        session = self.bot.helpers.get_db_session()
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

            # Check if they want to make the tag named 'list', or 'l' which are reserved keywords
            if tag_name.lower() in [
                "list",
                "l",
                "a",
                "add",
                "e",
                "edit",
                "d",
                "delete",
                "remove",
                "r",
                "i",
                "info",
                "raw",
            ]:
                return await ctx.send

            # Get the DB profile for the guild
            db_guild = await self.bot.helpers.db_get_guild(
                session, ctx.message.guild.id
            )
            # Get the DB profile for the user
            db_user = await self.bot.helpers.db_get_user(session, ctx.message.author.id)
            new_tag = models.Tags(
                server=db_guild, owner=db_user, name=tag_name, content=str(tag_content)
            )
            try:
                session.add(new_tag)
                session.commit()
                if new_tag:
                    return await ctx.send(f"Successfully created tag **{tag_name}**.")
            except exc.IntegrityError:
                session.rollback()
                session.close()
                return await ctx.send(
                    f"Sorry, a tag named **{tag_name}** already exists."
                )

        except discord.HTTPException as err:
            set_sentry_scope(ctx)
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Database error adding tag '{tag_name}'. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
            session.rollback()
        except Exception as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Error responding to {ctx.command} for tag '{tag_name}'. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        finally:
            session.close()

    @commands.guild_only()
    @has_guild_permissions(manage_messages=True)
    @tag.command(aliases=["e", "E"])
    async def edit(self, ctx, tag_name: str, *, tag_content: commands.clean_content):
        """Edits an existing tag for the guild. Everything after the tag name is used as the tag content. Everyone, here and role mentions are escaped to prevent abuse.

        Example:

        tag edit tagname this is a test tag
        with a new line **and bold formatting**

        Requires Permission: Manage Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        tag_name: str
            The name of the tag to edit.
        tag_content: str
            The content for the new tag.
        """

        session = self.bot.helpers.get_db_session()
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

            # Get the tag where tag name and guild ID match
            tag = (
                session.query(models.Tags)
                # Links the Server and Note table to get the Guild
                .join(models.Server, models.Server.id == models.Tags.server_id)
                .filter(
                    models.Server.discord_id == ctx.message.guild.id,
                    models.Tags.name == tag_name.strip(),
                )
                .first()
            )
            if not tag:
                return await ctx.send(
                    f"Sorry, unable to find a tag named **{tag_name}**."
                )

            tag.content = str(tag_content)
            session.commit()
            return await ctx.send(f"Successfully edited tag **{tag_name}**.")

        except discord.HTTPException as err:
            set_sentry_scope(ctx)
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Database error editing tag '{tag_name}'. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
            session.rollback()
        except Exception as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Error responding to {ctx.command} for tag '{tag_name}'. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        finally:
            session.close()

    @commands.guild_only()
    @has_guild_permissions(manage_messages=True)
    @tag.command(aliases=["d", "D", "remove", "r", "R"])
    async def delete(self, ctx, tag_name: str):
        """Deletes the specified tag.

        Example:

        tag delete tagname

        Requires Permission: Manage Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        tag_name: str
            The name of the tag to delete.
        """

        session = self.bot.helpers.get_db_session()
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

            # Get the tag where tag name and guild ID match
            tag = (
                session.query(models.Tags)
                # Links the Server and Note table to get the Guild
                .join(models.Server, models.Server.id == models.Tags.server_id)
                .filter(
                    models.Server.discord_id == ctx.message.guild.id,
                    models.Tags.name == tag_name.strip(),
                )
                .first()
            )
            if not tag:
                return await ctx.send(
                    f"Sorry, unable to find a tag named **{tag_name}**."
                )

            # Confirm the action
            confirm = await self.bot.prompt.send(
                ctx,
                f"Are you sure you want to delete **{tag_name}** with *{tag.uses}* uses?",
            )
            if confirm is False or None:
                return await ctx.send("Aborting tag deletion.")
            elif confirm:
                session.delete(tag)
                session.commit()
                return await ctx.send(f"Successfully deleted tag **{tag_name}**.")

        except discord.HTTPException as err:
            set_sentry_scope(ctx)
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Database error deleting tag '{tag_name}'. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
            session.rollback()
        except Exception as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Error responding to {ctx.command} for tag '{tag_name}'. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        finally:
            session.close()

    @commands.guild_only()
    @has_guild_permissions(send_messages=True)
    @tag.command()
    async def raw(self, ctx, tag_name: str):
        """Gets the raw content of the tag. This allows easy copy/pasting when editing a tag.

        Example:

        tag raw tagname

        Requires Permission: Send Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        tag_name: str
            The name of the tag to get.
        """

        session = self.bot.helpers.get_db_session()
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

            # Get the tag where tag name and guild ID match
            tag = (
                session.query(models.Tags)
                # Links the Server and Note table to get the Guild
                .join(models.Server, models.Server.id == models.Tags.server_id)
                .filter(
                    models.Server.discord_id == ctx.message.guild.id,
                    models.Tags.name == tag_name.strip(),
                )
                .first()
            )
            if not tag:
                return await ctx.send(
                    f"Sorry, unable to find a tag named **{tag_name}**."
                )

            transformations = {
                re.escape(c): "\\" + c for c in ("*", "`", "_", "~", "\\", "<")
            }

            def replace(obj):
                return transformations.get(re.escape(obj.group(0)), "")

            pattern = re.compile("|".join(transformations.keys()))
            await ctx.send(pattern.sub(replace, tag.content))

        except discord.HTTPException as err:
            set_sentry_scope(ctx)
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Database error getting raw info for tag '{tag_name}'. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
            session.rollback()
        except Exception as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Error responding to {ctx.command} for tag '{tag_name}'. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        finally:
            session.close()

    @commands.guild_only()
    @has_guild_permissions(send_messages=True)
    @tag.command(aliases=["i", "I"])
    async def info(self, ctx, tag_name: str):
        """Gets info about a specific tag. This includes tag name, owner, and number of uses.

        Example:

        tag info tagname

        Requires Permission: Send Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        tag_name: str
            The name of the tag to get.
        """

        session = self.bot.helpers.get_db_session()
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

            # Get the tag where tag name and guild ID match
            tag = (
                session.query(
                    models.Tags.name, models.Tags.uses, models.User, models.Tags.created
                )
                # Links the User and Tag table to get the User
                .join(models.User, models.User.id == models.Tags.owner_id)
                # Links the Server and Tag table to get the Guild
                .join(models.Server, models.Server.id == models.Tags.server_id)
                # Filters where the guilds Discord ID matches
                # and the tag name matches
                .filter(
                    models.Tags.name == tag_name.strip(),
                    models.Server.discord_id == ctx.message.guild.id,
                ).first()
            )
            if not tag:
                return await ctx.send(
                    f"Sorry, unable to find a tag named **{tag_name}**."
                )
            # Get the user object
            user = await self.bot.helpers.get_member_or_user(
                tag.User.discord_id, ctx.message.guild
            )
            # Create the embed
            embed = discord.Embed(
                colour=discord.Colour.blurple(),
                title=f"Tag Name: {tag.name}",
                timestamp=tag.created,
            )
            embed.set_author(name=f"{user} ({user.id})", icon_url=user.avatar_url)
            embed.add_field(name="Owner", value=f"<@{user.id}>")
            embed.add_field(name="Uses", value=str(tag.uses))
            embed.set_footer(text="Tag creation")
            await ctx.send(embed=embed)

        except discord.HTTPException as err:
            set_sentry_scope(ctx)
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Database error getting info for tag '{tag_name}'. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
            session.rollback()
        except Exception as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Error responding to {ctx.command} for tag '{tag_name}'. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        finally:
            session.close()

    @commands.guild_only()
    @has_guild_permissions(send_messages=True)
    @tag.command(aliases=["l", "L"])
    async def list(self, ctx):
        """Lists all tags in the guild. Shows tag name and number of uses.

        Example:

        tag list

        Requires Permission: Send Messages

        Parameters
        -----------
        ctx: context
            The context message involved.
        """

        session = self.bot.helpers.get_db_session()
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

            # Get the tag where tag name and guild ID match
            tags = (
                session.query(models.Tags.name, models.Tags.uses)
                # Links the Server and Tag table to get the Guild
                .join(models.Server, models.Server.id == models.Tags.server_id)
                # Filters where the guilds Discord ID matches
                .filter(models.Server.discord_id == ctx.message.guild.id).order_by(
                    desc(models.Tags.uses)
                )
            )
            if not tags:
                return await ctx.send(f"Sorry, this guild has no tags.")

            # Create list for pagination
            embed_result_entries = []
            footer_text = "List of all tags."
            for tag in tags:
                # Format the embed
                data_title = f"Name: {tag.name}"
                data_value = f"Uses: {tag.uses:,}"
                embed_result_entries.append([data_title, data_value])

            p = FieldPages(
                ctx,
                per_page=10,
                entries=embed_result_entries,
                mm_channel=ctx.message.channel,
            )
            p.embed.color = 0xFFFC9C
            p.embed.set_author(
                name=f"All tags for: {ctx.message.guild} ({ctx.message.guild.id})",
                icon_url=ctx.message.guild.icon_url,
            )
            p.embed.set_footer(text=footer_text)
            await p.paginate()

        except discord.HTTPException as err:
            set_sentry_scope(ctx)
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except exc.DBAPIError as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Database error listing all tags. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
            session.rollback()
        except Exception as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Error responding to {ctx.command}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        finally:
            session.close()


def setup(bot):
    bot.add_cog(Tags(bot))
