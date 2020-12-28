import sys
import typing
from datetime import datetime

import discord


async def user_action(
    bot,
    channel: str,
    member: discord.Member,
    action: str,
    text: str = "",
    author: typing.Optional[discord.Member] = None,
    guild: discord.Guild = None,
):
    # Log the action
    try:
        if not guild:
            guild = member.guild
        # Try and get the temp logs channel
        logs = discord.utils.get(guild.text_channels, name=f"{channel}-temp")

        if not logs:
            # If there is no temp logs channel, try the normal logs channel
            logs = discord.utils.get(guild.text_channels, name=channel)
            if not logs:
                return
    except Exception as err:
        return bot.log.exception(
            f"Error getting logs channel. {sys.exc_info()[0].__name__}: {err}"
        )

    # Checks if the bot can even send messages in that channel
    if not (
        logs.permissions_for(logs.guild.me).send_messages
        and logs.permissions_for(logs.guild.me).embed_links
    ):
        return bot.log.debug(
            f"Missing Permissions to log {action} in Guild: {logs.guild.id} | Channel: {logs.id}"
        )

    # Create the embed of info
    if len(text) > 0:
        text = "\n" + text
    color = bot.constants.log_colors["user_action"].get(
        action, bot.constants.log_colors["user_action"]["_default"]
    )
    embed = discord.Embed(
        color=color,
        timestamp=datetime.utcnow(),
        description=f"**Member:** {member} ({member.id})\n"
        f"**Action:** {action}"
        f"{text}",
    )
    if not author:
        author = member.guild.me
    embed.set_author(name=f"{author} ({author.id})", icon_url=author.avatar_url)
    embed.set_thumbnail(url=member.avatar_url)

    return await logs.send(embed=embed)
