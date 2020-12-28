import sys

import discord
from discord.ext import commands


class Role(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.guild_only()
    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role(self, ctx):
        """Base for the Role command."""

        self.bot.log.info(
            f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
        )

        await ctx.send(
            "This is the base role command. Use `role add`, or `role remove` for further functionality. To see what roles the user has use `userstats userID`."
        )

    @commands.guild_only()
    @role.command(aliases=["a", "A"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def add(self, ctx, user_id: str, *, role: str):
        """Adds a role to a member.

        Example:

        role add @wumpus#0000 role name
        role a userID role name

        Requires Permission: Manage Roles

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_id: str
            The user/member the role change is for.
        role: str
            The name of the role you want to adjust.
        """

        self.bot.log.info(
            f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
        )

        try:
            member = await self.bot.helpers.get_member_or_user(
                user_id, ctx.message.guild
            )
            if not member:
                return await ctx.send(
                    f"Unable to find the requested member. Please make sure the user ID or @ mention is valid."
                )
            if not isinstance(member, discord.Member):
                return await ctx.send(
                    f"Unable to find the requested member in this server."
                )

            guild_role = discord.utils.find(
                lambda r: r.name.lower() == role.lower().strip(),
                ctx.message.guild.roles,
            )

            if not guild_role:
                return await ctx.message.author.send(
                    f"Unable to find a role named `{role}`"
                )

            if ctx.author.top_role.position <= guild_role.position:
                return await ctx.send(
                    f"Sorry {ctx.author.mention}, but you can only add roles below your highest role."
                )

            await member.add_roles(guild_role)
            await ctx.send(
                f"Successfully added the role '**{guild_role.name}**' to {member}."
            )

        except discord.Forbidden:
            await ctx.send(
                "Unable to add the role. The bot ran into a permissions error. This could be caused by the role being above the bots highest role."
            )
        except discord.HTTPException as err:
            self.bot.log.exception(
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

    @commands.guild_only()
    @role.command(aliases=["delete", "r", "d"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def remove(self, ctx, user_id: str, *, role: str):
        """Removes a role from a member.

        Example:

        role remove @wumpus#0000 role name
        role r userID role name
        role d userID role name

        Requires Permission: Manage Roles

        Parameters
        -----------
        ctx: context
            The context message involved.
        user_id: str
            The user/member the role change is for.
        role: str
            The name of the role you want to adjust.
        """
        self.bot.log.info(
            f"CMD {ctx.command} called by {ctx.message.author} ({ctx.message.author.id})"
        )

        try:
            member = await self.bot.helpers.get_member_or_user(
                user_id, ctx.message.guild
            )
            if not member:
                return await ctx.send(
                    f"Unable to find the requested member. Please make sure the user ID or @ mention is valid."
                )
            if not isinstance(member, discord.Member):
                return await ctx.send(
                    f"Unable to find the requested member in this server."
                )

            guild_role = discord.utils.find(
                lambda r: r.name.lower() == role.lower().strip(),
                ctx.message.guild.roles,
            )

            if not guild_role:
                return await ctx.message.author.send(
                    f"Unable to find a role named `{role}`"
                )

            if ctx.author.top_role.position <= guild_role.position:
                return await ctx.send(
                    f"Sorry {ctx.author.mention}, but you can only remove roles below your highest role."
                )

            await member.remove_roles(guild_role)
            await ctx.send(
                f"Successfully removed the role '**{guild_role.name}**' from {member}."
            )
        except discord.Forbidden:
            await ctx.send(
                f"Unable to remove the role. The bot ran into a permissions error. This could be caused by the role being above the bots highest role."
            )
        except discord.HTTPException as err:
            self.bot.log.exception(
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
    bot.add_cog(Role(bot))
