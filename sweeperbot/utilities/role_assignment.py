import sys

import discord
from discord.ext import commands
from sqlalchemy.exc import DBAPIError

from sweeperbot.db import models


class RoleAssignment(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.roles = {}
        session = self.bot.helpers.get_db_session()
        try:
            # Get guild settings based on the bot ID
            # Theoretically there should only be one mod mail server per bot, if there is more than one, we're fucked.
            db_roles = (
                session.query(
                    models.Server,
                    models.RoleAssignment.message_id,
                    models.RoleAssignment.emoji_id,
                    models.RoleAssignment.role_id,
                )
                .join(
                    models.Server, models.Server.id == models.RoleAssignment.server_id
                )
                .all()
            )
            if not db_roles:
                self.bot.log.debug(
                    f"RoleAssignment: No roles found in database to track"
                )
                return

            for assignment in db_roles:
                guild_id = assignment.Server.discord_id
                message_id = assignment.message_id
                emoji_id = assignment.emoji_id
                role_id = assignment.role_id
                self.bot.log.debug(
                    f"RoleAssignment: {guild_id} | {message_id} | {emoji_id} - {role_id}"
                )

                # Check if the guild key exists, if not, create it
                if guild_id not in self.roles:
                    self.roles[guild_id] = {}
                    self.bot.log.debug(
                        f"RoleAssignment: Created new server_id dict for: {guild_id}"
                    )

                # Check if the message key exists, if not, create it
                if message_id not in self.roles[guild_id]:
                    self.roles[guild_id].update({message_id: {}})
                    self.bot.log.debug(
                        f"RoleAssignment: Created new message_id dict for: {message_id}"
                    )

                # Now let's update the message id dictionary with a list of the emoji's to role's
                # If the emoji_id exists, it will update with new role_id value, otherwise it'll add a new key:value
                self.roles[guild_id][message_id].update({emoji_id: role_id})
                self.bot.log.debug(
                    f"RoleAssignment: Created new emoji_id dict for eid: {emoji_id} | rid: {role_id}"
                )

            # Now that we're done loading everything, print the dict of roles
            self.bot.log.debug(f"RoleAssignment: {self.roles}")

        except DBAPIError as err:
            self.bot.log.exception(
                f"RoleAssignment: Database Error processing saved role assignments. {sys.exc_info()[0].__name__}: {err}"
            )
            session.rollback()
        except Exception as err:
            self.bot.log.exception(
                f"RoleAssignment: Unknown exception initializing role assignments. {sys.exc_info()[0].__name__}: {err}"
            )
        finally:
            session.close()

    async def process_role(self, guild_id, channel_id, message_id, user_id, emoji):
        # Check if the server even has any roles to manage
        if guild_id and guild_id not in self.roles:
            self.bot.log.debug(
                f"RoleAssignment (process_role): No guild_id found for mid: {message_id}"
            )
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            self.bot.log.debug(
                f"RoleAssignment (process_role): No guild returned for mid: {message_id}"
            )
            return

        # Get the channel
        channel = self.bot.get_channel(channel_id)
        self.bot.log.debug(
            f"RoleAssignment (process_role): Found channel ({channel.id}) for mid: {message_id}"
        )

        # Get the member from the user_id
        member = await self.bot.helpers.get_member_or_user(user_id, guild)
        self.bot.log.debug(
            f"RoleAssignment (process_role): Found member ({member.id}) for mid: {message_id}"
        )

        # If we have a member and it's of member type
        if member and isinstance(member, discord.Member):
            if (
                message_id  # and we have a message id
                and (
                    message_id in self.roles[guild_id]
                )  # and the message_id in the guild roles dict
                and emoji  # and we have an emoji
                and (
                    emoji.id in self.roles[guild_id][message_id]
                )  # and the emoji.id is in the guild.message dict
            ):
                # Get the role_id for the emoji.id
                role_id = self.roles[guild_id][message_id][emoji.id]
                if not role_id:
                    return
                # Now get the role from the guild
                role = guild.get_role(role_id)
                if not role:
                    self.bot.log.debug(
                        f"RoleAssignment (process_role): No role found for emoji.id: {emoji.id} | role_id: {role_id}"
                    )
                # Now that we have the member, and the role that goes to the emoji, let's see if we need to add or rem
                try:
                    if role in member.roles:
                        # Remove role
                        await member.remove_roles(role)
                        self.bot.log.debug(
                            f"RoleAssignment (process_role): Removed role_id: {role_id} to {member.id}"
                        )
                        # Remove the reaction
                        await self.remove_reaction(
                            channel.id, message_id, emoji, member.id
                        )
                        # Let them know we changed their roles
                        msg = await channel.send(
                            f"Hello {member.mention} - We have now __removed__ the role **{role.name}**."
                        )
                        # Delete in channel after period of time to not clog the channel
                        await msg.delete(delay=10)
                    else:
                        # Add role
                        await member.add_roles(role)
                        self.bot.log.debug(
                            f"RoleAssignment (process_role): Added role_id: {role_id} to {member.id}"
                        )
                        # Remove the reaction
                        await self.remove_reaction(
                            channel.id, message_id, emoji, member.id
                        )
                        # Let them know we changed their roles
                        msg = await channel.send(
                            f"Hello {member.mention} - We have now __added__ the role **{role.name}**."
                        )
                        # Delete in channel after period of time to not clog the channel
                        await msg.delete(delay=10)
                except discord.Forbidden as err:
                    if err.code == 50013:
                        try:
                            await channel.send(
                                f"There is an error managing that role. Please inform the server staff to make sure the bot has Manage Roles permission and the role is below the bot in the roles list."
                            )
                        except discord.Forbidden as err:
                            if err.code == 50013:
                                await member.send(
                                    f"There's an error managing that role. Please inform the server staff to make sure the bot has Manage Roles permission and the role is below the bot in the roles list."
                                )

        else:
            self.bot.log.debug(
                f"RoleAssignment (process_role): member ({member.id}) is type {type(member)}"
            )

    async def remove_reaction(self, channel_id, message_id, emoji, member_id):
        # Uses raw HTTP methods so we just pass the data
        await self.bot.http.remove_reaction(
            channel_id, message_id, f"{emoji.name}:{emoji.id}", member_id
        )
        self.bot.log.debug(
            f"RoleAssignment (remove_reaction): /{channel_id}/{message_id}/{emoji.name}:{emoji.id}/{member_id}"
        )

    def add_to_dict(self, guild_id, message_id, emoji_id, role_id):
        # Check if the guild key exists, if not, create it
        if guild_id not in self.roles:
            self.roles[guild_id] = {}
            self.bot.log.debug(
                f"RoleAssignment: Created new server_id dict for: {guild_id}"
            )

        # Check if the message key exists, if not, create it
        if message_id not in self.roles[guild_id]:
            self.roles[guild_id].update({message_id: {}})
            self.bot.log.debug(
                f"RoleAssignment: Created new message_id dict for: {message_id}"
            )

        # Now let's update the message id dictionary with a list of the emoji's to role's
        # If the emoji_id exists, it will update with new role_id value, otherwise it'll add a new key:value
        self.roles[guild_id][message_id].update({emoji_id: role_id})
        self.bot.log.debug(
            f"RoleAssignment: Created new emoji_id dict for eid: {emoji_id} | rid: {role_id}"
        )

    def delete_from_dict(self, guild_id, message_id, emoji_id):
        # Check if the guild key exists, if not, return
        if guild_id not in self.roles:
            self.bot.log.debug(
                f"RoleAssignment: Unable to find server_id in dict for: {guild_id}"
            )
            return

        # Check if the message key exists, if not, return
        if message_id not in self.roles[guild_id]:
            self.bot.log.debug(
                f"RoleAssignment: Unable to find message_id in dict for: {message_id}"
            )
            return

        # Check if the emoji exists (it should), if so delete
        if emoji_id in self.roles[guild_id][message_id]:
            self.roles[guild_id][message_id].pop(emoji_id)
            self.bot.log.debug(
                f"RoleAssignment: Deleted emoji_id from dict for eid: {emoji_id} | mid: {message_id}"
            )
            return
