import datetime
import re
import sys

import discord
import parsedatetime as pdt
import pytz
import requests
from discord.ext import commands
from sentry_sdk import configure_scope
from sqlalchemy import asc
from sqlalchemy.exc import DBAPIError
from urlextract import URLExtract

from sweeperbot.db import models

utc = pytz.UTC


class AntiSpam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Set the cooldown for on_message - too many too quickly and they get muted
        # 1. Initialize the global cooldown settings
        global_cd_settings = self.bot.cooldown_settings.get("antispam_on_message")
        message_rate = global_cd_settings.message_rate
        cooldown_time = global_cd_settings.cooldown_time
        self.global_cd_on_message = commands.CooldownMapping.from_cooldown(
            message_rate, cooldown_time, commands.BucketType.user
        )
        self.bot.log.debug(
            f"AntiSpam:on_message Global Cooldown set to {self.global_cd_on_message._cooldown.rate} msgs per {self.global_cd_on_message._cooldown.per} sec"
        )

        # Initializes the URL Extractor then updates the list of TLDs
        self.url_extractor = URLExtract()
        self.url_extractor.update()
        # Load the Anti Spam Services and their Regex's
        self.antispam_services = []
        self.antispam_pending_mutes = {}
        self.bot.log.info(f"Loaded AntiSpam")

    def get_all_urls_from_string(self, input_string):
        return self.url_extractor.find_urls(input_string)

    async def set_cooldown_buckets(self):
        # Initialize the cooldown dict holding all cooldowns
        self.cooldowns = {}
        session = self.bot.helpers.get_db_session()
        try:
            for guild in self.bot.guilds:
                # Get guild settings
                settings = await self.bot.helpers.get_one_guild_settings(
                    session, guild.id
                )

                cd_on_message_rate = settings.cd_on_message_rate
                cd_on_message_time = settings.cd_on_message_time

                # Initialize the dict for the guild
                self.cooldowns[guild.id] = {}

                # If the guild has custom cooldown setting:
                if cd_on_message_rate and cd_on_message_time:
                    # Create the cooldown mapping
                    cd_on_message = commands.CooldownMapping.from_cooldown(
                        cd_on_message_rate, cd_on_message_time, commands.BucketType.user
                    )
                    # Set the cooldowns
                    self.cooldowns[guild.id].update({"cd_on_message": cd_on_message})
                    self.bot.log.debug(
                        f"AntiSpam:on_message Using Custom Cooldown, set to {cd_on_message._cooldown.rate} msgs per {cd_on_message._cooldown.per} sec for {guild} ({guild.id})"
                    )
                # If no custom setting, use global
                else:
                    # Set the cooldowns
                    self.cooldowns[guild.id].update(
                        {"cd_on_message": self.global_cd_on_message}
                    )
                    self.bot.log.debug(
                        f"AntiSpam:on_message Using Global Cooldown, set to {self.global_cd_on_message._cooldown.rate} msgs per {self.global_cd_on_message._cooldown.per} sec for {guild} ({guild.id})"
                    )
        except DBAPIError as err:
            self.bot.log.exception(
                f"Database Error in AntiSpam Module setting all cooldowns. {sys.exc_info()[0].__name__}: {err}"
            )
            session.rollback()
        except Exception as err:
            self.bot.log.exception(
                f"Generic Error in AntiSpam Module setting all cooldowns. {sys.exc_info()[0].__name__}: {err}"
            )
        finally:
            # Close this database session
            session.close()

    async def antispam_process_message(self, message):
        try:
            # Check if server has a bypass role
            bypass_role = None
            settings = self.bot.guild_settings.get(message.guild.id)
            if settings and settings.bot_bypass_role:
                bypass_role = message.guild.get_role(settings.bot_bypass_role)
            # Check if they are exempt from antispam based on bypass role or being a mod
            if (
                message.author.bot
                or message.author.permissions_in(message.channel).manage_messages
                or (bypass_role and bypass_role in message.author.roles)
            ):
                return self.bot.log.debug(
                    f"AntiSpam: The user {message.author} ({message.author.id}) is exempt from AntiSpam processing"
                )

            # Check if user is on cooldown/rate limited, issue temp mute
            if settings and settings.antispam_quickmsg:
                # 1. First we need to check if there is the guild specific cooldown mapping
                try:
                    cd_on_message = self.cooldowns.get(message.guild.id)[
                        "cd_on_message"
                    ]
                # If no cooldown mapping, use the global one
                # this will cover cases where quickmsg setting is enabled but no custom setting
                except Exception as err:
                    cd_on_message = self.global_cd_on_message
                # 2. Get the bucket
                bucket = cd_on_message.get_bucket(message)
                retry_after = bucket.update_rate_limit()
                if retry_after:
                    # Add the user to the Pending Mute dict so we don't try and execute multiple times
                    # Check if the guild key exists, if not, create it
                    if message.guild.id not in self.antispam_pending_mutes:
                        self.antispam_pending_mutes[message.guild.id] = []
                    # Check if user is in pending mutes for the guild
                    if (
                        message.author.id
                        not in self.antispam_pending_mutes[message.guild.id]
                    ):
                        self.antispam_pending_mutes[message.guild.id].append(
                            message.author.id
                        )
                        # Delete the message, help the mods clean up
                        await message.delete()
                    else:
                        self.bot.log.debug(
                            f"AntiSpam: User {message.author} ({message.author.id}) already pending a mute. Ignoring"
                        )
                        # Delete the message, help the mods clean up
                        await message.delete()
                        return
                    # Since there is not a pending mute, continue
                    # Log on cooldown
                    self.bot.log.debug(
                        f"AntiSpam: User {message.author} ({message.author.id}) is on cooldown/rate limited, and unable to send messages. They will be muted. Expires: {retry_after:0.2f} seconds"
                    )
                    # Mute user for spam
                    # Get mute command
                    mute_cmd = self.bot.get_command("mute")
                    # Create a bot message so that it logs under the bot and creates proper context
                    bot_msg = await message.channel.send(
                        f"Please do not spam or send too many messages too quickly."
                    )
                    ctx = await self.bot.get_context(bot_msg)
                    # Create the datetime object
                    calendar = pdt.Calendar(version=pdt.VERSION_CONTEXT_STYLE)
                    now = datetime.datetime.now(datetime.timezone.utc)
                    # Choose the mute length. If custom setting, use that, otherwise default
                    if settings and settings.antispam_mute_time:
                        mute_length = settings.antispam_mute_time
                    else:
                        mute_length = "1h"
                    mute_time_dt, status = calendar.parseDT(mute_length, sourceTime=now)
                    # Run the mute command
                    await mute_cmd(
                        ctx,
                        user_id=message.author.id,
                        mute_time=mute_time_dt.replace(tzinfo=utc),
                        reason=self.bot.constants.antispam_quickmsg,
                    )
                    # Removes the pending mute
                    self.antispam_pending_mutes[message.guild.id].remove(
                        message.author.id
                    )
                    # Check if a mod channel is set and alert there.
                    if settings and settings.mod_channel:
                        mod_channel = discord.utils.get(
                            message.guild.text_channels, id=settings.mod_channel,
                        )
                        if mod_channel:
                            try:
                                await mod_channel.send(
                                    f"""The following user was automatically muted for spam:\n\n**Msg Author:** {message.author.mention} ({message.author.id})\n**Last Message ({message.id}):** {message.jump_url}\n**Content:**\n> {message.content[:1700]}"""
                                )
                            # If there is an error, just ignore, nothing we can do
                            except Exception as err:
                                pass
                    return
                # User not rate limited, continue

            # Get the URLs in the message so we can process each one
            urls = self.get_all_urls_from_string(message.content)
            if not urls:
                self.bot.log.debug(
                    f"AntiSpam: Skipping - No URL's found in Msg ID: {message.id}"
                )
                return
            for orig_url in urls:
                # Fix if the start of the URL isn't exactly 'http' but like 'b1http'
                orig_url = re.sub(r"^.*?http", "http", orig_url)
                # If the orig_url doesn't start with 'http://' then add it, otherwise we get MissingSchema error
                orig_url_clean = (
                    "http://" + orig_url
                    if not orig_url.startswith("http")
                    else orig_url
                )
                url = None
                try:
                    # Check for Redirection. Want to only process the last URL in case someone hides behind redirection.
                    # Allow redirects obv, and set a timeout to prevent long url hang
                    try:
                        res = requests.head(
                            orig_url_clean, allow_redirects=True, timeout=10.000
                        )
                        url = res.url
                    except requests.exceptions.ReadTimeout:
                        # If there is a ReadTimeout error trying to load the URL, just use it as-is
                        self.bot.log.debug(
                            f"AntiSpam: ReadTimeout error processing redirects for url '{orig_url_clean}' - using original"
                        )
                        url = orig_url_clean
                    except requests.exceptions.TooManyRedirects:
                        # If there is a TooManyRedirects error trying to load the URL, just use it as-is
                        self.bot.log.debug(
                            f"AntiSpam: TooManyRedirects error processing redirects for url '{orig_url_clean}' - using original"
                        )
                        url = orig_url_clean
                    # Now we need to run the URL through each service regex to see what matches
                    service_id = None
                    service_name = None
                    service_regex = None
                    regex_result = None
                    for service in self.antispam_services:
                        service_id = service.id
                        service_name = service.service
                        service_regex = service.regex
                        self.bot.log.debug(
                            f"AntiSpam | service_name: {service_name} | service_regex: {service_regex} | url: {url}"
                        )
                        regex_result = re.search(service_regex, url)
                        self.bot.log.debug(
                            f"AntiSpam | service_name: {service_name} | regex_result: {regex_result}"
                        )
                        if regex_result:
                            # If we get a match for the URL to the service, we need to break out and process the service
                            break

                    # If there is a match, now we need to process it to see if it should be allowed or not
                    if regex_result:
                        result_allowed, spam_guild = await self.antispam_process_rules(
                            service_id, service_name, message, regex_result.group(0)
                        )
                        # If the result/message/service is allowed for this url, then continue looping through in case
                        # there is something else not allowed
                        if result_allowed:
                            continue
                        elif result_allowed is False:
                            # 1. Log it
                            debug_mode = await self.log_antispam(
                                message, service_name, regex_result.group(0), spam_guild
                            )
                            # If debug mode is false aka disabled then we delete the message.
                            if debug_mode is False:
                                try:
                                    await message.delete()
                                except discord.errors.NotFound:
                                    # Message is not found, likely already deleted, nothing we need to worry about
                                    pass
                                except discord.Forbidden:
                                    mod_channel = discord.utils.get(
                                        message.guild.text_channels,
                                        id=settings.mod_channel,
                                    )
                                    if mod_channel:
                                        await mod_channel.send(
                                            f"""The following message is flagged by the AntiSpam rules, however I was unable to automatically remove it.\n\n**Msg Author:** {message.author.mention} ({message.author.id})\n**Flag Reason:** {service_name}\n**Link:** {message.jump_url}"""
                                        )
                            # 2. Return so we don't double dip
                            return
                    else:
                        # TO DO - Log the URL to a database so we have record of url's that we aren't handling for anti
                        # spam which we could potentially handle in the future if the url is popular enough
                        return self.bot.log.debug(
                            f"AntiSpam | No Regex match found for: {url if url else orig_url}"
                        )

                except requests.exceptions.ConnectTimeout as err:
                    self.bot.log.warning(
                        f"URL Timeout for {orig_url} | {sys.exc_info()[0].__name__}: {err}"
                    )
                except Exception as err:
                    with configure_scope() as scope:
                        scope.set_extra(
                            "guild_id", f"{message.guild.id if message.guild else None}"
                        )
                        scope.set_extra(
                            "message_id", f"{message.id if message else None}"
                        )
                        scope.user = {
                            "id": f"{message.author.id if message.author else None}",
                            "username": f"{message.author if message.author else None}",
                        }
                    self.bot.log.exception(
                        f"Exception processing AntiSpam for the url: {orig_url} | {sys.exc_info()[0].__name__}: {err}"
                    )
        except discord.HTTPException as err:
            self.bot.log.exception(
                f"Discord HTTP Error processing AntiSpam Message. {sys.exc_info()[0].__name__}: {err}"
            )
        except Exception as err:
            self.bot.log.exception(
                f"Error processing AntiSpam Message. {sys.exc_info()[0].__name__}: {err}"
            )

    # Holds all the logic for processing the rules
    async def antispam_process_rules(
        self, service_id, service_name, message, regex_match
    ):
        # Setup base variable to track whether the service is allowed or not. By default we are going to allow it
        allowed = True
        # We need to handle some cases where we need to lookup the "regex_match" and translate it to an ID
        # For example a regex_match could be a discord invite code, we need to look that up and get the
        # guild ID it goes to
        spam_guild = None
        if service_id == 1 or service_name.lower() == "discord":
            try:
                # Splits the regex_match by the slash in the URL, then gets the last item of that URL which would
                # be the discord invite code, then tells the Discord API to fetch by invite code instead of URL
                # due to the Discord.py not being able to handle some of the new Discord URLs
                invite_code = regex_match.split("/")[-1]
                invite = await self.bot.fetch_invite(invite_code, with_counts=True)
                if invite:
                    spam_guild = invite.guild
                    if spam_guild:
                        self.bot.log.debug(
                            f"AntiSpam | spam_guild: {spam_guild} ({spam_guild.id})"
                        )
                else:
                    # So we found a Discord invite code, but it didn't return a valid guild, meaning bad invite code.
                    # Return out so we don't punish the user for something invalid
                    self.bot.log.debug(f"AntiSpam: Invite not found: {regex_match}")
                    return allowed, spam_guild
            except discord.errors.NotFound:
                # So we found a Discord invite code, but it didn't return a valid guild, in this case the code wasn't
                # found on discord's service, meaning the code expired.
                # Return out so we don't punish the user for something invalid
                self.bot.log.debug(
                    f"AntiSpam: Not Found Error: Invite not found: {regex_match}"
                )
                return allowed, spam_guild

        session = self.bot.helpers.get_db_session()
        try:
            # Get the DB profile for the guild
            db_guild = await self.bot.helpers.db_get_guild(session, message.guild.id)
            # First we want to get the rules that the server has related to this service
            # Ordered by ascending order as we go broad to narrowed rule specificity
            antispam_service_rules = (
                session.query(models.AntiSpamServerSettings)
                .filter(
                    models.AntiSpamServerSettings.server == db_guild,
                    models.AntiSpamServerSettings.service_id == service_id,
                )
                .order_by(asc(models.AntiSpamServerSettings.rule_id))
                .all()
            )
            # Now we need to check what rules they have for this service, and process each one individually
            # and come up to a conclusion on how the rule should be enforced after all rules are tallied
            for rule in antispam_service_rules:
                # Set the variables for each rule
                server_id = rule.server_id
                service_id = rule.service_id
                rule_id = rule.rule_id
                service_match_text = rule.service_match_text
                service_match_ids = rule.service_match_ids
                channel_ids = rule.channel_ids
                user_ids = rule.user_ids
                service_value = rule.service_value
                # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                self.bot.log.debug(
                    f"AntiSpam | Rule: {rule_id} | Svc: {service_name} | MsgID: {message.id} | Current Status Allowed: {allowed}"
                )
                # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                # Now let's go through each rule per Order of Operations
                # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                # Rule 1 is Block All
                if rule_id == 1:
                    allowed = False
                    self.bot.log.debug(
                        f"AntiSpam | Rule: {rule_id} | Svc: {service_name} | SvcMatch: {regex_match} | MsgID: {message.id} | Allowed: {allowed} | Block all"
                    )
                # Rule 2 is Allow All
                elif rule_id == 2:
                    allowed = True
                    self.bot.log.debug(
                        f"AntiSpam | Rule: {rule_id} | Svc: {service_name} | SvcMatch: {regex_match} | MsgID: {message.id} | Allowed: {allowed} | Allow all"
                    )
                # Rule 3 is Block only in specific list of channels, otherwise passthrough
                elif rule_id == 3:
                    if channel_ids and message.channel.id in channel_ids:
                        allowed = False
                        self.bot.log.debug(
                            f"AntiSpam | Rule: {rule_id} | Svc: {service_name} | SvcMatch: {regex_match} | MsgID: {message.id} | Allowed: {allowed} | In blocked list"
                        )
                # Rule 4 is Allow only in specific list of channels, blocked otherwise
                elif rule_id == 4:
                    if channel_ids and message.channel.id in channel_ids:
                        allowed = True
                        self.bot.log.debug(
                            f"AntiSpam | Rule: {rule_id} | Svc: {service_name} | SvcMatch: {regex_match} | MsgID: {message.id} | Allowed: {allowed} | In allowed list"
                        )
                    elif channel_ids and message.channel.id not in channel_ids:
                        allowed = False
                        self.bot.log.debug(
                            f"AntiSpam | Rule: {rule_id} | Svc: {service_name} | SvcMatch: {regex_match} | MsgID: {message.id} | Allowed: {allowed} | Not in allowed list"
                        )
                    elif channel_ids is None:
                        # We're having a default allowed here in case they have an empty list of channels
                        allowed = True
                        self.bot.log.debug(
                            f"AntiSpam | Rule: {rule_id} | Svc: {service_name} | SvcMatch: {regex_match} | MsgID: {message.id} | Allowed: {allowed} | Channel list null, default allow"
                        )
                elif rule_id == 5:
                    # Rule 5 is allow the specific link only in specific list of channels, blocked otherwise
                    if (
                        (service_match_text and regex_match in service_match_text)
                        or (
                            (spam_guild and service_match_ids)
                            and spam_guild.id in service_match_ids
                        )
                    ) and (channel_ids and message.channel.id in channel_ids):
                        allowed = True
                        self.bot.log.debug(
                            f"AntiSpam | Rule: {rule_id} | Svc: {service_name} | SvcMatch: {regex_match} | MsgID: {message.id} | ChanID: {message.channel.id} | Allowed: {allowed} | service_match_text: {service_match_text} | channel_ids: {channel_ids} | In allow list"
                        )
                    else:
                        # otherwise we'll block it assuming it's not in the allowed list
                        allowed = False
                        self.bot.log.debug(
                            f"AntiSpam | Rule: {rule_id} | Svc: {service_name} | SvcMatch: {regex_match} | MsgID: {message.id} | ChanID: {message.channel.id} | Allowed: {allowed} | service_match_text: {service_match_text} | channel_ids: {channel_ids} | Default block"
                        )
                elif rule_id == 6:
                    # Rule 6 is block the specific link only in specific list of channels, otherwise passthrough
                    if (
                        (service_match_text and regex_match in service_match_text)
                        or (
                            (spam_guild and service_match_ids)
                            and spam_guild.id in service_match_ids
                        )
                    ) and (channel_ids and message.channel.id in channel_ids):
                        allowed = False
                        self.bot.log.debug(
                            f"AntiSpam | Rule: {rule_id} | Svc: {service_name} | SvcMatch: {regex_match} | MsgID: {message.id} | ChanID: {message.channel.id} | Allowed: {allowed} | service_match_text: {service_match_text} | channel_ids: {channel_ids} | In block list"
                        )
                # Allow specific link of service everywhere
                elif rule_id == 7:
                    if (
                        (service_match_text and regex_match in service_match_text)
                        or (service_match_ids and regex_match in service_match_ids)
                        or (
                            (spam_guild and service_match_ids)
                            and spam_guild.id in service_match_ids
                        )
                    ):
                        if user_ids:
                            # If only certain users are allowed to post it, then further check that
                            if message.author.id in user_ids:
                                allowed = True
                                self.bot.log.debug(
                                    f"AntiSpam | Rule: {rule_id} | Svc: {service_name} | SvcMatch: {regex_match} | MsgID: {message.id} | Allowed: {allowed} | service_match_text: {service_match_text} | service_match_ids: {service_match_ids} | spam_guild: {spam_guild.id if spam_guild else None}"
                                )
                        else:
                            allowed = True
                            self.bot.log.debug(
                                f"AntiSpam | Rule: {rule_id} | Svc: {service_name} | SvcMatch: {regex_match} | MsgID: {message.id} | Allowed: {allowed} | service_match_text: {service_match_text} | service_match_ids: {service_match_ids} | spam_guild: {spam_guild.id if spam_guild else None}"
                            )
                # Block specific link of service everywhere
                elif rule_id == 8:
                    if (service_match_text and regex_match in service_match_text) or (
                        (spam_guild and service_match_ids)
                        and spam_guild.id in service_match_ids
                    ):
                        allowed = False
                        self.bot.log.debug(
                            f"AntiSpam | Rule: {rule_id} | Svc: {service_name} | SvcMatch: {regex_match} | MsgID: {message.id} | Allowed: {allowed} | service_match_text: {service_match_text} | service_match_ids: {service_match_ids} | spam_guild: {spam_guild.id if spam_guild else None}"
                        )

                self.bot.log.debug(f"AntiSpam | Current Status Allowed: {allowed}")

        # TO DO - Add a lot of exception handling around this code
        except DBAPIError as err:
            self.bot.log.exception(
                f"Database Error in AntiSpam Module. {sys.exc_info()[0].__name__}: {err}"
            )
            session.rollback()
        except Exception as err:
            self.bot.log.exception(
                f"Generic Error in AntiSpam Module. {sys.exc_info()[0].__name__}: {err}"
            )
        finally:
            # Close this database session
            session.close()
            # Return whether the message is allowed or not
            return allowed, spam_guild

    async def log_antispam(self, message, service_name, regex_result, spam_guild=None):
        debug_mode = True
        try:
            antispam_channel = discord.utils.get(
                message.guild.text_channels, name="antispam-debug-logs"
            )
            # If there isn't a debug logs channel, try and get the normal one
            if not antispam_channel:
                antispam_channel = discord.utils.get(
                    message.guild.text_channels, name="antispam-logs"
                )
                if antispam_channel:
                    debug_mode = False
                else:
                    return debug_mode

            # Create the embed of info
            description = (
                f"**Message Deleted:** {'Yes' if debug_mode is False else 'No'}\n"
            )
            description += f"**Match:** {regex_result}\n"
            description += (
                f"**Member:** {message.author.mention} ({message.author.id})\n"
            )
            if service_name == "Discord" and spam_guild:
                description += f"**Guild:** {spam_guild.name} ({spam_guild.id})\n"
            description += f"**Channel:** {message.channel.mention} | **Cat:** {message.channel.category.name if message.channel.category else None}\n"
            description += f"**Message Timestamp:** {message.created_at.replace(microsecond=0)} UTC\n"
            description += f"**Message Link:** {message.jump_url}\n"
            description += f"**Message:** ({message.id})\n\n"
            description += f"{message.clean_content[:1680]}"
            embed = discord.Embed(
                color=0x1BA8F1 if debug_mode is False else 0x006D5B,
                title=f"AntiSpam Alert | {service_name}",
                timestamp=datetime.datetime.utcnow(),
                description=description,
            )
            embed.set_author(
                name=f"{message.author} ({message.author.id})",
                icon_url=message.author.avatar_url,
            )

            # Send the log
            try:
                await antispam_channel.send(
                    f"{message.author} ({message.author.id})", embed=embed
                )
            except discord.Forbidden:
                self.bot.log.warning(
                    f"Missing permissions to send in {antispam_channel.name} ({antispam_channel.id}) in guild {antispam_channel.guild.name} ({antispam_channel.guild.id})"
                )
        except Exception as err:
            self.bot.log.exception(
                f"AntiSpam: Generic error sending logging Message. {sys.exc_info()[0].__name__}: {err}"
            )
        finally:
            return debug_mode
