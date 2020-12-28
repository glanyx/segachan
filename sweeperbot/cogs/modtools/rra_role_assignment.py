import sys

import discord
from discord.ext import commands
from sqlalchemy.exc import DBAPIError, IntegrityError

from sweeperbot.db import models


class ReactionRoleAssignment(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.has_permissions(manage_roles=True)
    @commands.group(invoke_without_command=True)
    async def rra(self, ctx):
        """Reaction Role Assignment. This is the base command and shouldn't be called.

        Please use either 'rra add' or 'rra delete'

        Requires Permission: Manage Roles
        """
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            await ctx.send(
                "This is the base Reaction Role Assignment command. Use `rra add`, or `rra delete` for further functionality."
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

    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    @rra.command(aliases=["a", "A"])
    async def add(
        self,
        ctx,
        channel: discord.TextChannel,
        message_id: int,
        emoji: discord.Emoji,
        *,
        role_id: str,
    ):
        """Takes the Message ID on the Role Assignment message, the Emoji the user will click to toggle the role,
        and the Role ID/Name that will be managed. This then sets to give the role when they click the emoji.

        Note: The bot must have access to the Emoji and cannot be any Discord default emoji's.

        Example:
        .rra add #channel message_id :emoji_mention: role_name/role_id
        .rra add #test 722659508803076097 :online: ambassador

        Requires Permission: Manage Roles

        Parameters
        -----------
        ctx: context
            The context message involved.
        channel: discord.TextChannel
            The channel the Role Assignment message is in.
        message_id: int
            The Message ID on the Role Assignment message.
        emoji: emoji
            Emoji the user will click to toggle the role.
        role_id: str
            The name or ID of the role to manage. This is case-insensitive.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # If user tries to mention @everyone then deny it.
            if role_id.lower() == "@everyone":
                return await ctx.message.author.send(
                    f"Sorry, you can't give the everyone role"
                )

            # First try to convert it to an int and get role by ID
            try:
                role = ctx.message.guild.get_role(int(role_id))
            except ValueError:
                # If it's a string, find the role, case-insensitive removing leading and trailing whitespace.
                role = discord.utils.find(
                    lambda r: r.name.lower() == role_id.lower().strip(),
                    ctx.message.guild.roles,
                )

            if not role:
                return await ctx.message.author.send(
                    f"Unable to find a role named `{role_id}`. Please try using the role ID directly."
                )

            # Now that we have the role, let's create the DB entry
            # Get the DB profile for the guild
            db_guild = await self.bot.helpers.db_get_guild(
                session, ctx.message.guild.id
            )

            db_rra = models.RoleAssignment(
                server=db_guild,
                message_id=message_id,
                emoji_id=emoji.id,
                role_id=role.id,
            )
            session.add(db_rra)
            session.commit()

            # and update the cache dict
            self.bot.assignment.add_to_dict(
                ctx.message.guild.id, message_id, emoji.id, role.id
            )

            # Add the reaction to the message
            try:
                await self.bot.http.add_reaction(
                    channel.id, message_id, f"{emoji.name}:{emoji.id}"
                )
                await ctx.send(
                    f"Role Reaction Assignment has been setup for emoji {emoji} to provide the role '{role.name}'"
                )
            except Exception as err:
                self.bot.log.warning(
                    f"Error adding the reaction. {sys.exc_info()[0].__name__}: {err}"
                )
                await ctx.send(
                    f"Role Reaction Assignment has been setup, however unable to add the emoji '{emoji.name}' to the message. Please do that yourself. When someone clicks the emoji they will be provided the role '{role.name}'"
                )

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except IntegrityError as err:
            self.bot.log.warning(
                f"RRA Duplicate Message {message_id}/Emoji {emoji.id} constraint. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"There was a database error setting that Role Reaction option. Try using the `rra delete` option then run the add again."
            )
            session.rollback()
        except DBAPIError as err:
            self.bot.log.exception(
                f"Error processing database add for RRA. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"There was a database error setting that Role Reaction option. Try using the `rra delete` option or a different emoji then run the add again. Error has already been reported to my developers."
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

    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    @rra.command(aliases=["d", "D"])
    async def delete(
        self, ctx, channel: discord.TextChannel, message_id: int, emoji: discord.Emoji,
    ):
        """Takes the Message ID on the Role Assignment message, the Emoji the user will click to toggle the role,
        and the Role ID/Name that will be managed. This then sets to give the role when they click the emoji.

        Note: The bot must have access to the Emoji and cannot be any Discord default emoji's.

        Example:
        .rra delete #channel message_id :emoji_mention:
        .rra delete #test 722659508803076097 :online:

        Requires Permission: Manage Roles

        Parameters
        -----------
        ctx: context
            The context message involved.
        channel: discord.TextChannel
            The channel the Role Assignment message is in.
        message_id: int
            The Message ID on the Role Assignment message.
        emoji: emoji
            Emoji the user will click to toggle the role.
        """

        session = self.bot.helpers.get_db_session()
        try:
            self.bot.log.info(
                f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
            )

            # Now that we have the role, let's create the DB entry
            # Get the DB profile for the guild
            db_guild = await self.bot.helpers.db_get_guild(
                session, ctx.message.guild.id
            )

            # Find the role in the DB
            db_role = (
                session.query(models.RoleAssignment)
                .filter(
                    models.RoleAssignment.server_id == db_guild.id,
                    models.RoleAssignment.message_id == message_id,
                    models.RoleAssignment.emoji_id == emoji.id,
                )
                .first()
            )

            # If db_role exists
            if not db_role:
                return await ctx.send(
                    f"No Role Assignment found for that Message, and Emoji combination."
                )
            # Confirm the removal
            confirm = await self.bot.prompt.send(
                ctx, f"Are you sure you want to remove the Role Assignment for {emoji}?"
            )
            if confirm:
                session.delete(db_role)
                session.commit()

                # and update the cache dict
                self.bot.assignment.delete_from_dict(
                    ctx.message.guild.id, message_id, emoji.id
                )

                # delete own reaction
                try:
                    await self.bot.http.remove_own_reaction(
                        channel.id, message_id, f"{emoji.name}:{emoji.id}"
                    )
                # Can error if it can't remove its own reaction such as if it doesn't exist
                except discord.Forbidden:
                    pass

                # tell user done
                await ctx.send(f"Successfully deleted Role Assignment for: {emoji}")
            elif confirm is False:
                return await ctx.send("Cancelling request.")
            elif confirm is None:
                return await ctx.send("Request timed out.")

        except discord.HTTPException as err:
            self.bot.log.error(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except IntegrityError as err:
            self.bot.log.warning(
                f"RRA Duplicate Message {message_id}/Emoji {emoji.id} constraint. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"There was a database error setting that Role Reaction option. Try using the `rra delete` option then run the add again."
            )
            session.rollback()
        except DBAPIError as err:
            self.bot.log.exception(
                f"Error processing database add for RRA. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"There was a database error setting that Role Reaction option. Try using the `rra delete` option or a different emoji then run the add again. Error has already been reported to my developers."
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
    bot.add_cog(ReactionRoleAssignment(bot))
