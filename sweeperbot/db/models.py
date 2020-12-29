"""This module defines the db models used by SweeperBot"""
import sqlalchemy
from citext import CIText
from sqlalchemy import (
    BigInteger,
    Boolean,
    DECIMAL,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Table,
    ARRAY,
)
from sqlalchemy.ext.declarative import declared_attr, declarative_base
from sqlalchemy.orm import relationship, backref
from sqlalchemy.schema import UniqueConstraint, Index


class SweeperBase(object):
    """This class provides the defaults for each class inheriting it."""

    @declared_attr
    def __tablename__(cls):
        """The table will be named a lower case version of its class name"""
        return cls.__name__.lower()

    id = Column(Integer, primary_key=True)
    created = Column(DateTime(timezone=True), server_default=sqlalchemy.sql.func.now())
    updated = Column(DateTime(timezone=True), onupdate=sqlalchemy.sql.func.now())


Base = declarative_base(cls=SweeperBase)


# Many-to-many relationships
clubbotrels = Table(
    "clubbotrels",
    Base.metadata,
    Column("clubbot_id", Integer, ForeignKey("clubbot.id")),
    Column("clubbotuser_id", Integer, ForeignKey("clubbotuser.id")),
)


# Normal table models
class Server(Base):
    discord_id = Column(BigInteger, nullable=False, unique=True, index=True)
    name = Column(CIText, nullable=True)


class User(Base):
    discord_id = Column(
        BigInteger,
        nullable=False,
        unique=True,
        index=True,
        comment="A user's unique discord id",
    )
    birthday = Column(DateTime)


class ServerAdminRels(Base):
    server_id = Column(Integer, ForeignKey("server.id"))
    server = relationship(Server, backref=backref("serveradminrels", uselist=True))
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship(User, backref=backref("serveradminrels", uselist=True))
    UniqueConstraint(server_id, user_id, name="serveradminrels_serverid_userid_unique")


class ServerModRels(Base):
    server_id = Column(Integer, ForeignKey("server.id"))
    server = relationship(Server, backref=backref("servermodrels", uselist=True))
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship(User, backref=backref("servermodrels", uselist=True))
    UniqueConstraint(server_id, user_id, name="servermodrels_serverid_userid_unique")


class Alias(Base):
    name = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship(User, backref=backref("alias", uselist=True))


class Action(Base):
    mod_id = Column(Integer, ForeignKey("user.id"))
    mod = relationship(User, backref=backref("action", uselist=True))
    server_id = Column(Integer, ForeignKey("server.id"))
    server = relationship(Server, backref=backref("action", uselist=True))


class Note(Base):
    text = Column(String)
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship(User, backref=backref("note", uselist=True))
    action_id = Column(Integer, ForeignKey("action.id"))
    action = relationship(Action, backref=backref("note", uselist=True))
    server_id = Column(Integer, ForeignKey("server.id"))
    server = relationship(Server, backref=backref("note", uselist=True))


class Warn(Base):
    text = Column(String)
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship(User, backref=backref("warn", uselist=True))
    action_id = Column(Integer, ForeignKey("action.id"))
    action = relationship(Action, backref=backref("warn", uselist=True))
    server_id = Column(Integer, ForeignKey("server.id"))
    server = relationship(Server, backref=backref("warn", uselist=True))


class Mute(Base):
    text = Column(String)
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship(User, backref=backref("mute", uselist=True))
    action_id = Column(Integer, ForeignKey("action.id"))
    action = relationship(Action, backref=backref("mute", uselist=True))
    server_id = Column(Integer, ForeignKey("server.id"))
    server = relationship(Server, backref=backref("mute", uselist=True))
    expires = Column(DateTime(timezone=True))
    old_roles = Column(ARRAY(BigInteger))


class Kick(Base):
    text = Column(String)
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship(User, backref=backref("kick", uselist=True))
    action_id = Column(Integer, ForeignKey("action.id"))
    action = relationship(Action, backref=backref("kick", uselist=True))
    server_id = Column(Integer, ForeignKey("server.id"))
    server = relationship(Server, backref=backref("kick", uselist=True))


class Ban(Base):
    text = Column(String)
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship(User, backref=backref("ban", uselist=True))
    action_id = Column(Integer, ForeignKey("action.id"))
    action = relationship(Action, backref=backref("ban", uselist=True))
    server_id = Column(Integer, ForeignKey("server.id"))
    server = relationship(Server, backref=backref("ban", uselist=True))
    expires = Column(DateTime(timezone=True))


class Statistic(Base):
    server_id = Column(Integer, ForeignKey("server.id"))
    server = relationship(Server, backref=backref("statistic", uselist=True))
    total_users = Column(Integer)
    concurrent_users = Column(Integer)
    total_voice_users = Column(Integer)


class Message(Base):
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship(User, backref=backref("message", uselist=True))
    server_id = Column(Integer, ForeignKey("server.id"))
    server = relationship(Server, backref=backref("message", uselist=True))
    channel_id = Column(BigInteger)
    channel_name = Column(String)
    message_id = Column(BigInteger, unique=True)
    message_body = Column(String)
    Index(message_body, postgresql_using="gin")


class ModMailMessage(Base):
    primary_server_id = Column(Integer, ForeignKey("server.id"))
    primary_server = relationship(Server, foreign_keys=[primary_server_id])
    mm_server_id = Column(Integer, ForeignKey("server.id"))
    mm_server = relationship(Server, foreign_keys=[mm_server_id])
    mm_channel_id = Column(BigInteger, nullable=False)
    user_channel_id = Column(BigInteger, nullable=False)
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship(User, backref=backref("modmailmessage", uselist=True))
    message_id = Column(BigInteger, nullable=False)
    message = Column(String)
    file_links = Column(ARRAY(String))
    from_mod = Column(Boolean, nullable=False)
    Index(message, postgresql_using="gin")


class Blacklist(Base):
    server_id = Column(Integer, ForeignKey("server.id"))
    server = relationship(Server, backref=backref("botblacklist", uselist=True))
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship(User, backref=backref("botblacklist", uselist=True))
    blacklisted = Column(Boolean, nullable=False, default=False)
    UniqueConstraint(server_id, user_id, name="blacklist_serverid_userid_unique")


class VoiceLog(Base):
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship(User, backref=backref("voicelog", uselist=True))
    server_id = Column(Integer, ForeignKey("server.id"))
    server = relationship(Server, backref=backref("voicelog", uselist=True))
    vc_old_name = Column(String)
    vc_old_id = Column(BigInteger)
    vc_old_users_ids = Column(ARRAY(BigInteger))
    vc_new_name = Column(String)
    vc_new_id = Column(BigInteger)
    vc_new_users_ids = Column(ARRAY(BigInteger))
    event_type = Column(String)


# Start ClubBot Stuff
class ClubBotUser(Base):
    author_id = Column(CIText(), unique=True)
    author = Column(CIText())
    security_code = Column(CIText(), nullable=True)
    reddit_discord_verified = Column(Boolean)
    discord_id = Column(String, nullable=True, unique=True)


class ClubBot(Base):
    author_id = Column(CIText())
    author = Column(CIText())
    subreddit = Column(CIText())
    subreddit_id = Column(CIText())
    welcome_pm_sent = Column(Boolean)
    date_added = Column(DateTime(timezone=True))
    first_post_id = Column(String)
    member_num = Column(Integer)
    UniqueConstraint(author_id, subreddit_id, name="clubbot_unique_user_sub")


class ClubBotDiscordSetting(Base):
    subreddit = Column(String)
    subreddit_id = Column(String)
    d_server_id = Column(String)
    d_user_role_id = Column(String)
    UniqueConstraint(
        subreddit_id,
        d_server_id,
        name="clubbot_discord_settings_subreddit_id_d_server_id_uindex",
    )


class ClubBotPosts(Base):
    author_id = Column(CIText())
    author = Column(CIText())
    club_subreddit_id = Column(CIText())
    club_subreddit = Column(CIText())
    post_id = Column(CIText())
    post_created_utc = Column(BigInteger)
    date_added = Column(DateTime(timezone=True))
    UniqueConstraint(post_id, club_subreddit_id, name="clubbot_post_club_id_pk")


# End ClubBot Stuff


class ServerSetting(Base):
    server_id = Column(Integer, ForeignKey("server.id"))
    server = relationship(Server, backref=backref("serversetting", uselist=True))
    bot_prefix = Column(ARRAY(String))
    modmail_server_id = Column(BigInteger)
    modmail_unanswered_cat_id = Column(BigInteger)
    modmail_in_progress_cat_id = Column(BigInteger)
    muted_role = Column(BigInteger)
    bot_bypass_role = Column(BigInteger)
    mod_channel = Column(BigInteger)
    wordfilter_data = Column(JSON)
    appeals_invite_code = Column(String)
    welcome_msg = Column(String)
    footer_msg = Column(String)
    antispam_quickmsg = Column(Boolean, default=False)
    antispam_mass_mentions = Column(Boolean, default=False)
    antispam_twitch = Column(Boolean, default=False)
    antispam_discord_invites = Column(Boolean, default=False)
    antispam_mixer = Column(Boolean, default=False)
    antispam_patreon = Column(Boolean, default=False)
    antispam_paypal = Column(Boolean, default=False)
    antispam_wordfilter = Column(Boolean, default=False)
    bot_id = Column(BigInteger)
    admin_role = Column(BigInteger)
    mod_role = Column(BigInteger)
    request_channel = Column(BigInteger)
    request_channel_allowed = Column(ARRAY(BigInteger))
    activity_status = Column(ARRAY(String))
    activity_status_enabled = Column(Boolean, default=False)
    enabled = Column(
        Boolean,
        default=True,
        comment="Whether the bot is in the server, thus loading the settings",
    )
    antispam_quickmsg_modmail = Column(Boolean, default=True)
    welcome_msg_enabled = Column(Boolean, default=False)
    on_join_role_id = Column(BigInteger)
    on_join_role_enabled = Column(Boolean, default=False)
    cd_on_message_rate = Column(
        DECIMAL,
        comment="on_message event number of messages per cd_on_message_time before on cooldown",
    )
    cd_on_message_time = Column(
        DECIMAL, comment="on_message event cooldown time, in seconds"
    )
    antispam_mute_time = Column(
        String,
        comment="Time to mute someone if antispam is tripped. Format is same as mute, e.g. '1h', '1d', '30m', etc",
    )


class Tags(Base):
    server_id = Column(Integer, ForeignKey("server.id"), index=True)
    server = relationship(Server, backref=backref("tags", uselist=True))
    owner_id = Column(Integer, ForeignKey("user.id"))
    owner = relationship(User, backref=backref("tags", uselist=True))
    uses = Column(Integer, default=0)
    name = Column(CIText(), index=True)
    content = Column(String)

    sqlalchemy.Index("tag_uniq_idx", name, server_id, unique=True)


class AntiSpamServices(Base):
    """This holds a list of services like 'Twitch' or 'Discord' or 'Quick Msg' and any RegEx used for detecting the
    service, a description of the service, and whether it's enabled to be used by the bot as a service type
    to offer the users. This way we can prep the bot by loading services at anytime via the database but not
    allow servers to set rules related to the service until we're ready."""

    service = Column(CIText(), unique=True)
    regex = Column(String, nullable=True)
    enabled = Column(Boolean, default=False)
    description = Column(String, nullable=True)


class AntiSpamRules(Base):
    """This is more for the relationship/enum type ability were we have a rule number and a description.
    The handling of what the rule means will be done in the code itself."""

    description = Column(String, nullable=True)


class AntiSpamServerSettings(Base):
    """
    While ideally we would enforce a unique constraint on Server + Service + Rule, this isn't possible via the database.
    It's possible that Server ABC wants to only allow Discord Invites from servers 1,2,3 in channels X,Y,Z. Server A
    also wants to only allow Discord Invites from server 9 in channels W,X,Y. If database uniqueness was enforced they
    wouldn't be able to apply the same rule to the same service, just to different channels. Instead we need to account
    for this in code to check to make sure that there are not any conflicting rules. Additional constraints will be
    added in code to further constrain to prevent a single service from being impacted by two conflicting rules. For
    example you can't have a 'Block all Discord' links and an 'Allow all Discord' links at the same time.

    As described in the column comments, the service_match_text is meant to be an arroy of text that would be applicable
    to the rule. E.g. if the rule is to allow certain twitch channels only in certain discord channels you would find
    this column with a list of twitch channel names. You would also find channel_ids filled with an array of
    Discord channel ID's that the twitch links can only be posted in.
    """

    server_id = Column(
        Integer,
        ForeignKey("server.id"),
        index=True,
        comment="The guild/server that the setting/rule applies to.",
    )
    server = relationship(
        Server, backref=backref("antispamserversettings", uselist=True)
    )
    service_id = Column(
        Integer,
        ForeignKey("antispamservices.id"),
        index=True,
        comment="The service the rule is related to, e.g. 'Twitch', or 'Discord', etc.",
    )
    service = relationship(
        AntiSpamServices, backref=backref("antispamserversettings", uselist=True)
    )
    rule_id = Column(
        Integer,
        ForeignKey("antispamrules.id"),
        index=True,
        comment="The rule that is being applied.",
    )
    rule = relationship(
        AntiSpamRules, backref=backref("antispamserversettings", uselist=True)
    )
    service_match_text = Column(
        ARRAY(String),
        nullable=True,
        comment="A list of text that the setting/rule should match. For example could be a list of twitch usernames to allow to be posted.",
    )
    service_match_ids = Column(
        ARRAY(BigInteger),
        nullable=True,
        comment="A list of IDs that the setting/rule should match. For example could be a list of guild IDs that are Discord Invite whitelisted, etc.",
    )
    channel_ids = Column(
        ARRAY(BigInteger),
        nullable=True,
        comment="A list of channel IDs that the setting/rule would apply to. For e.g. if we want to allow the service_match(text/ids) to work in specific channels, the channel IDs would be listed here.",
    )
    user_ids = Column(
        ARRAY(BigInteger),
        nullable=True,
        comment="A list of user IDs that the setting/rule would apply to. For e.g. if we want to allow only certain users to post invites from certain guilds, or certain users to list certain twitch links, their IDs would be listed here.",
    )
    service_value = Column(
        Integer,
        nullable=True,
        comment="Any integer value associated. Such as number of mentions allowed, quick message rate limit (messages per time period), etc.",
    )


class Requests(Base):
    """Records the request and number of votes"""

    # Guilde the request is related to
    server_id = Column(Integer, ForeignKey("server.id"))
    server = relationship(Server, backref=backref("requests", uselist=True))
    # User that made the suggestion
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship(User, backref=backref("requests", uselist=True))
    # ID of the message
    message_id = Column(BigInteger, unique=True)
    # Number of upvotes
    upvotes = Column(Integer, default=0)
    # Number of downvotes
    downvotes = Column(Integer, default=0)
    # The text of the suggestion
    text = Column(CIText())


class Reminder(Base):
    creator_user_id = Column(BigInteger, comment="User that created the reminder")
    remind_user_id = Column(
        Integer,
        ForeignKey("user.id"),
        comment="User that the reminder is for, can be different than creator",
    )
    remind_user = relationship(User, backref=backref("reminder", uselist=True))
    server_id = Column(
        Integer, ForeignKey("server.id"), comment="Server the reminder belongs to"
    )
    server = relationship(Server, backref=backref("reminder", uselist=True))
    expires = Column(DateTime(timezone=True))
    text = Column(String)


class MemberLogs(Base):
    # Guild the member join/part is related to
    server_id = Column(Integer, ForeignKey("server.id"))
    server = relationship(Server, backref=backref("memberlogs", uselist=True))
    # User that the member join/part is related to
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship(User, backref=backref("memberlogs", uselist=True))
    type = Column(String, comment="Whether they are Joining or Parting the server")
    timestamp = Column(DateTime(timezone=True))

    sqlalchemy.Index(
        "mbrlogs_uniq_idx", user_id, server_id, type, timestamp, unique=True
    )


class RoleAssignment(Base):
    """Information needed for processing Reaction based Role Assignment.

    There is a unique index between the message id, emoji id, and role id.
    You can only use the same emoji on the same message once, so we want a one to one relationship with role id.
    We then track the message id to know what message to watch the emoji/reaction on to make sure we don't
    process role changes if the emoji is used elsewhere."""

    # Guild the Role Assignment is for
    server_id = Column(Integer, ForeignKey("server.id"))
    server = relationship(Server, backref=backref("roleassignment", uselist=True))
    # ID of the message the Role Assignment relates to
    message_id = Column(BigInteger)
    # ID of the Emoji being used to relate to the role
    emoji_id = Column(BigInteger)
    # ID of the Role that the Emoji relates to
    role_id = Column(BigInteger)

    sqlalchemy.Index("roleassignment_uniq_idx", message_id, emoji_id, unique=True)


class Cooldowns(Base):
    """Various cooldowns that can be adjusted in the Database to impact the app. Mostly when custom cooldowns are set"""

    name = Column(CIText(), unique=True, index=True, comment="The name of the cooldown")
    message_rate = Column(
        DECIMAL, comment="Number of messages per cooldown_time before on cooldown"
    )
    cooldown_time = Column(DECIMAL, comment="Cooldown time, in seconds")
