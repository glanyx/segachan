import sys
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands
from sqlalchemy.exc import DBAPIError

from sweeperbot.db import models


class Verify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(send_messages=True)
    @commands.guild_only()
    async def verify(self, ctx, security_code: Optional[str] = None):
        """Verifies a reddit user to a discord account for The Club Hub Discord server."""

        no_security_code_msg = "Please send a message to u/ClubBot on reddit with the subject 'security code' and anything can be in the body, then try again. **You may need to wait up to 5 minutes for the security code to be sent you you.** You can use this link for convenience: https://www.reddit.com/message/compose/?to=ClubBot&subject=security+code&message=please"

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
            try:
                await ctx.message.delete()
            except (discord.errors.Forbidden, discord.errors.NotFound):
                pass

            # If no security code
            if not security_code:
                try:
                    # Send use a DM
                    await ctx.message.author.send(no_security_code_msg)
                    # Let them know in channel we DM'd them
                    msg = await ctx.send(
                        f"Hello {ctx.message.author.mention} - Please check your DMs, I've sent you a message."
                    )
                    # Delete in channel after period of time to not clog the channel
                    await msg.delete(delay=20)
                except discord.Forbidden:
                    # If unable to DM them, send in channel
                    msg = await ctx.send(no_security_code_msg)
                    # Delete in channel after period of time to not clog the channel
                    await msg.delete(delay=60)
                # Regardless, return out of this code
                return

            club_user = (
                session.query(models.ClubBotUser)
                .filter(models.ClubBotUser.security_code == str(security_code))
                .first()
            )
            # If no user found with that security code
            if not club_user:
                await ctx.message.author.send(
                    "I was unable to find you based on the security code provided. Please make sure you are typing the code in all capitals and using the correct code."
                )
                msg = await ctx.send(
                    f"Hello {ctx.message.author.mention} - Please check your DMs, I've sent you a message."
                )
                # Delete in channel after period of time to not clog the channel
                await msg.delete(delay=20)
                return

            # For now, converting the database discord id into an int from text due to the reddit bots storing as text
            # If the user is already verified, then just fix their roles
            if (
                club_user.discord_id
                and int(club_user.discord_id) == ctx.message.author.id
                and club_user.reddit_discord_verified
            ):
                return await self.add_roles(
                    session, ctx.message.author, ctx.message.guild, club_user
                )

            # If the user is already verified but discord ID's don't match, send for manual verification
            if (
                club_user.reddit_discord_verified
                and club_user.discord_id
                and int(club_user.discord_id) != ctx.message.author.id
            ):
                return await ctx.send(
                    f"Hello <@&572940646101286922> - Please manually verify {ctx.message.author.mention} as their Discord ID's don't match what I have in the database."
                )

            # Update the verification status, remove the security code
            club_user.reddit_discord_verified = True
            club_user.discord_id = str(ctx.message.author.id)
            club_user.security_code = None
            session.commit()

            # Now that we have them marked as verified in the database, add their roles
            return await self.add_roles(
                session, ctx.message.author, ctx.message.guild, club_user
            )

        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error responding to {ctx.command} request via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
            )
            await ctx.send(
                f"Error processing {ctx.command}. Error has already been reported to my developers."
            )
        except DBAPIError as err:
            self.bot.log.exception(
                f"Error processing database query via Msg ID {ctx.message.id}. {sys.exc_info()[0].__name__}: {err}"
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

    async def add_roles(self, session, member, guild, club_user):
        verified_user_role = guild.get_role(534_899_799_783_243_807)
        # Get all the clubs they belong to
        # club_user.author_id
        clubs_user_belongs_to = (
            session.query(models.ClubBot)
            .filter(models.ClubBot.author_id == club_user.author_id)
            .all()
        )

        # Append all the clubs they belong to into a list
        subs_eligible = []
        for club in clubs_user_belongs_to:
            subs_eligible.append(club.subreddit_id)

        # Get the club discord settings
        # the guild id is a string in the database, but the library is an int
        clubs_discord_settings = (
            session.query(models.ClubBotDiscordSetting)
            .filter(models.ClubBotDiscordSetting.d_server_id == str(guild.id))
            .all()
        )

        # Get the club settings/role
        roles_to_add = []
        if verified_user_role:
            roles_to_add.append(verified_user_role)

        for club_setting in clubs_discord_settings:
            if club_setting.subreddit_id in subs_eligible:
                role = guild.get_role(int(club_setting.d_user_role_id))
                if role:
                    roles_to_add.append(role)

        # Checks if the only roles to add is either nothing, or just the verified role, then tell them not elgiible
        if len(roles_to_add) <= 1:
            return await member.send(
                f"Sorry, but I don't show you as being eligible to join any of our clubs. If this is a mistake, please leave a message in the request roles channel and a Discord Mod will assist as soon as they can."
            )

        # Now that we have all the roles to add, let's add them to the user and set their nickname
        # Since the user is new we can use member.edit which sets the info, but if user already has roles
        # then we'd want to use member.add_roles
        await member.edit(
            nick=f"{club_user.author}.",
            roles=roles_to_add,
            reason=f"Adding eligible club roles",
        )
        # Remove the verified user role so it doesn't get listed
        roles_to_add.remove(verified_user_role)
        temp_roles = [role.name for role in roles_to_add]
        temp_roles_str = ", ".join(temp_roles)

        try:
            # Log the verification
            logs_channel = discord.utils.get(
                member.guild.text_channels, name="verification-logs"
            )
            # Create the embed
            embed = discord.Embed(color=0xF5BC91, timestamp=datetime.utcnow())
            embed.set_author(name=f"{member} ({member.id})", icon_url=member.avatar_url)
            embed.add_field(
                name="Nickname", value=f"{club_user.author}.\n{member.mention}"
            )
            embed.add_field(name="Roles Added", value=f"{temp_roles_str}.")
            # Send embed of verification details to verification logs channel
            if logs_channel:
                await logs_channel.send(embed=embed)
        except Exception as err:
            self.bot.log.exception(
                f"Error creating/sending embed of verification history"
            )

        channel = discord.utils.get(
            member.guild.text_channels, id=531_543_370_041_131_008
        )
        # Welcome the user to the server
        await channel.send(
            f"Please welcome our newest member {member.mention} who has access to the following clubs:\n\n{temp_roles_str}"
        )


def setup(bot):
    bot.add_cog(Verify(bot))
