import sys

import discord
from discord.ext import commands


class AllRoles(commands.Cog):
    """List all roles on the server."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def allroles(self, ctx):
        """List all roles on the server."""

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

            # little logic to split into embeds with 2000 characters max
            output = []
            roles = sorted(
                ctx.message.guild.roles,
                key=lambda role: len(role.members),
                reverse=True,
            )
            for role in roles:
                output.append(
                    f"**{len(role.members):,}** | {role.mention} ({role.id}) \n"
                )

            out = ""
            for line in output:
                out += line
                if len(out) > 1900:
                    embed = discord.Embed(
                        title=f"Roles for {ctx.message.guild.name}", description=out
                    )
                    await ctx.send(embed=embed)
                    out = ""

            if len(out) != 0:
                embed = discord.Embed(
                    title=f"Roles for {ctx.message.guild.name}", description=out
                )
                await ctx.send(embed=embed)

        except discord.errors.Forbidden as err:
            self.bot.log.warning(
                f"Bot missing perms. {ctx.command} via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.message.author.send(
                f"Bot is missing perms. Please make sure it has send messaages (to actually send the message), manage messages (to delete calling message), manage roles (to view the info), and embed links (to send the message) perms."
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
    bot.add_cog(AllRoles(bot))
