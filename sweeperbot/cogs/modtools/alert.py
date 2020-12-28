import sys
import typing

import discord
from discord.ext import commands

from sweeperbot.utilities.helpers import set_sentry_scope


class Alert(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def alert(
        self,
        ctx,
        channel: typing.Optional[discord.TextChannel] = None,
        *,
        role_name: str,
    ):
        """Send a message pinging the role specified. If a channel mention is
        provided then it will send to that channel.

        Requires Permission: Manage Roles

        Parameters
        -----------
        ctx: context
            The context message involved.
        channel: Optional[discord.TextChannel]
            The channel the alert should be sent to. If none specified uses current
            channel.
        role_name: str
            The name of the role to ping. This is case-insensitive.
        """
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
            # If no channel specified uses channel command was called from.
            if not channel:
                channel = ctx

            # If user tries to mention @everyone then deny it.
            if role_name.lower() == "@everyone":
                return await ctx.message.author.send(
                    f"lol you are really funny trying to mention `@everyone`. Sorry "
                    f"but I'm not permitted to do that."
                )

            # Finds the role, case-insensitive removing leading and trailing whitespace.
            try:
                role = discord.utils.find(
                    lambda r: r.name.lower() == role_name.lower().strip(),
                    ctx.message.guild.roles,
                )

                if not role:
                    return await ctx.message.author.send(
                        f"Unable to find a role named `{role_name}`"
                    )

                # If role is already mentionable then it mentions it and leaves
                # enable. If it wasn't mentionable in the first place it will enable
                # it, mentions it, then disables mentioning.
                try:
                    disable_mentions = True
                    if role.mentionable:
                        disable_mentions = False

                    await role.edit(mentionable=True)
                    await channel.send(f"Hello <@&{role.id}>")

                    if disable_mentions:
                        await role.edit(mentionable=False)
                except Exception as err:
                    self.bot.log.exception(
                        f"Error mentioning role named '{role_name} via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
                    )
                    await ctx.send(
                        f"Error processing {ctx.command}. Error has already been reported to my developers."
                    )
            except Exception as err:
                set_sentry_scope(ctx)
                self.bot.log.exception(
                    f"Error finding role named '{role_name}'. {sys.exc_info()[0].__name__}: {err}"
                )

        except discord.HTTPException as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Discord HTTP Error responding to {ctx.command}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except Exception as err:
            set_sentry_scope(ctx)
            self.bot.log.exception(
                f"Error responding to {ctx.command}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )


def setup(bot):
    bot.add_cog(Alert(bot))
