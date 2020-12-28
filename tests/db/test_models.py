"""Tests for db/models.py"""
from datetime import datetime
from random import randint
from uuid import uuid4
from os.path import abspath, dirname, join
import configparser

import pytest
from sqlalchemy import and_
from sweeperbot.db import models, manager

curdir = join(abspath(dirname(__file__)))
parentdir = join(curdir, "../../")

botconfig = configparser.ConfigParser()
botconfig.read(join(parentdir, "botconfig.ini"))

SESSION = None
BASE_USER = None
BASE_SERVER = None


@pytest.fixture(scope="session", autouse=True)
def setup_module():
    global SESSION, BASE_SERVER, BASE_USER
    SESSION = manager.get_session(botconfig, db_config="TestDatabase")
    BASE_USER = models.User(discord_id=randint(10, 10000))
    SESSION.add(BASE_USER)
    BASE_SERVER = models.Server(discord_id=randint(10, 10000))
    SESSION.add(BASE_SERVER)
    SESSION.commit()


# def teardown_module(module):
#     models.Base.metadata.drop_all(ENGINE)


def test_positive_create_user():
    """Create a user and verify it exists in the database"""
    discord_id = randint(10, 10000)
    new_user = models.User(discord_id=discord_id)
    SESSION.add(new_user)
    SESSION.commit()
    user = SESSION.query(models.User).filter(models.User.discord_id == discord_id).one()
    assert user.discord_id == discord_id
    assert user.created


def test_positive_update_user():
    """Create a user and update their birthday"""
    birthday = datetime.now()
    BASE_USER.birthday = birthday
    BASE_USER.mod_of.append(BASE_SERVER)
    SESSION.commit()
    user = SESSION.query(models.User).filter(models.User.id == BASE_USER.id).one()
    assert user.discord_id == BASE_USER.discord_id
    assert user.birthday == birthday
    assert BASE_SERVER in user.mod_of


def test_positive_create_server():
    discord_id = randint(10, 10000)
    new_server = models.Server(discord_id=discord_id)
    SESSION.add(new_server)
    SESSION.commit()
    server = (
        SESSION.query(models.Server)
        .filter(models.Server.discord_id == discord_id)
        .one()
    )
    assert server.discord_id == discord_id
    assert server.created


def test_positive_create_alias():
    """Create a user and alias, assigning the latter to the former"""
    discord_id = randint(10, 10000)
    new_user = models.User(discord_id=discord_id)
    SESSION.add(new_user)
    alias_text = "my cool alias#0000"
    new_alias = models.Alias(name=alias_text, user=new_user)
    SESSION.add(new_alias)
    SESSION.commit()
    assert (
        SESSION.query(models.Alias.name).filter(models.Alias.user == new_user).one()[0]
        == alias_text
    )


def test_positive_action_warn():
    """This test also covers Note, Mute, and Ban"""
    discord_id, warn_text = randint(10, 10000), "this is a test warning"
    logged_action = models.Action(mod=BASE_USER, server=BASE_SERVER)
    new_warn = models.Warn(
        text=warn_text,
        user=models.User(discord_id=discord_id),
        server=BASE_SERVER,
        action=logged_action,
    )
    SESSION.add(new_warn)
    SESSION.commit()
    user = SESSION.query(models.User).filter(models.User.discord_id == discord_id).one()
    assert new_warn in user.warn
    warn = SESSION.query(models.Warn).filter(models.Warn.user == user).first()
    assert warn.text == warn_text
    assert warn.action == logged_action


def test_positive_add_statistic():
    stats = {
        "total_users": randint(10, 10000),
        "concurrent_users": randint(10, 10000),
        "total_voice_users": randint(10, 10000),
        "snapshot_time": datetime.now(),
    }
    new_stat = models.Statistic(server=BASE_SERVER, **stats)
    SESSION.add(new_stat)
    SESSION.commit()
    result = (
        SESSION.query(models.Statistic)
        .filter(
            and_(
                models.Statistic.server_id == BASE_SERVER.id,
                models.Statistic.snapshot_time == stats["snapshot_time"],
            )
        )
        .first()
    )
    assert result.total_users == stats["total_users"]
    assert result.concurrent_users == stats["concurrent_users"]
    assert result.total_voice_users == stats["total_voice_users"]


def test_positive_message():
    message_details = {
        "message_id": randint(10, 10000),
        "message_body": str(uuid4()),
        "channel_id": randint(10, 10000),
        "channel_name": str(uuid4()),
    }
    new_message = models.Message(user=BASE_USER, server=BASE_SERVER, **message_details)
    SESSION.add(new_message)
    SESSION.commit()
    result = (
        SESSION.query(models.Message)
        .filter(models.Message.message_id == message_details["message_id"])
        .first()
    )
    assert result.message_body == message_details["message_body"]
    assert result.channel_id == message_details["channel_id"]
    assert result.channel_name == message_details["channel_name"]


def test_positive_direct_message():
    """Create a message and add it as a direct message"""
    message_details = {
        "message_id": str(uuid4()),
        "message_body": str(uuid4()),
        "channel_id": str(uuid4()),
        "channel_name": str(uuid4()),
    }
    new_message = models.Message(user=BASE_USER, server=BASE_SERVER, **message_details)
    SESSION.add(new_message)
    dm_channel_id, user_channel_id = str(uuid4()), str(uuid4())
    new_dm = models.DirectMessage(
        dm_server=BASE_SERVER,
        dm_channel_id=dm_channel_id,
        user_channel_id=user_channel_id,
        dm_message=new_message,
    )
    SESSION.add(new_dm)
    SESSION.commit()
    result = (
        SESSION.query(models.DirectMessage)
        .filter(models.DirectMessage.dm_channel_id == dm_channel_id)
        .first()
    )
    assert result.dm_message == new_message
    assert result.user_channel_id == user_channel_id
    assert result.dm_message.message_body == message_details["message_body"]


def test_positive_voicelog():
    v_log_details = {
        "vc_old_name": str(uuid4()),
        "vc_old_id": str(uuid4()),
        "vc_old_users_ids": str(uuid4()),
        "vc_new_name": str(uuid4()),
        "vc_new_id": str(uuid4()),
        "vc_new_users_ids": str(uuid4()),
        "event_type": str(uuid4()),
    }
    new_voicelog = models.VoiceLog(user=BASE_USER, server=BASE_SERVER, **v_log_details)
    SESSION.add(new_voicelog)
    SESSION.commit()
    result = (
        SESSION.query(models.VoiceLog)
        .filter(models.VoiceLog.event_type == v_log_details["event_type"])
        .first()
    )
    assert result.vc_old_id == v_log_details["vc_old_id"]
    assert result.vc_new_id == v_log_details["vc_new_id"]
    assert result.vc_new_users_ids == v_log_details["vc_new_users_ids"]


def test_positive_clubbotuser():
    cb_user_details = {
        "author_id": str(uuid4()),
        "author": str(uuid4()),
        "security_code": str(uuid4()),
        "reddit_discord_verified": True,
        "discord_id": str(uuid4()),
    }
    new_cb_user = models.ClubBotUser(**cb_user_details)
    SESSION.add(new_cb_user)
    SESSION.commit()
    result = (
        SESSION.query(models.ClubBotUser)
        .filter(models.ClubBotUser.security_code == cb_user_details["security_code"])
        .first()
    )
    assert result.author_id == cb_user_details["author_id"]
    assert result.reddit_discord_verified


def test_positive_clubbot():
    """Create a new club bot user and align it to a new club bot"""
    cb_user_details = {
        "author_id": str(uuid4()),
        "author": str(uuid4()),
        "security_code": str(uuid4()),
        "reddit_discord_verified": True,
        "discord_id": str(uuid4()),
    }
    new_cb_user = models.ClubBotUser(**cb_user_details)
    SESSION.add(new_cb_user)
    subreddit, subreddit_id = str(uuid4()), str(uuid4())
    new_clubbot = models.ClubBot(subreddit=subreddit, subreddit_id=subreddit_id)
    new_clubbot.users.append(new_cb_user)
    SESSION.add(new_clubbot)
    SESSION.commit()
    result = (
        SESSION.query(models.ClubBot)
        .filter(models.ClubBot.subreddit_id == subreddit_id)
        .first()
    )
    assert result.subreddit == subreddit
    assert new_cb_user in result.users


def test_serversetting():
    settings = {
        "bot_prefix": {"prefixes": [str(uuid4()), str(uuid4())]},
        "modmail_server_id": str(uuid4()),
        "muted_role": str(uuid4()),
        "bot_bypass_role": str(uuid4()),
        "wordfilter_data": {"test val": 1337},
        "appeals_invite_code": str(uuid4()),
        "welcome_msg": str(uuid4()),
        "footer_msg": str(uuid4()),
        "antispam_quickmsg": True,
        "antispam_mixer": True,
        "antispam_patreon": True,
    }
    new_settings = models.ServerSetting(server=BASE_SERVER, **settings)
    SESSION.add(new_settings)
    SESSION.commit()
    result = (
        SESSION.query(models.ServerSetting)
        .filter(
            and_(
                models.ServerSetting.server_id == BASE_SERVER.id,
                models.ServerSetting.welcome_msg == settings["welcome_msg"],
            )
        )
        .first()
    )
    assert result.bot_prefix == settings["bot_prefix"]
    assert result.modmail_server_id == settings["modmail_server_id"]
    assert result.antispam_mixer == settings["antispam_mixer"]
    assert result.antispam_twitch == False


def test_tags():
    name = str(uuid4())
    content = str(uuid4())
    new_tag = models.Tags(
        server=BASE_SERVER, owner=BASE_USER, name=name, content=content
    )
    SESSION.add(new_tag)
    SESSION.commit()
    result = (
        SESSION.query(models.Tags)
        .filter(
            and_(
                models.Tags.server_id == BASE_SERVER.id,
                models.Tags.name == name.upper(),
            )
        )
        .first()
    )
    assert result.name == name
    assert result.content == content
    assert result.owner == BASE_USER
    assert result.uses == 0
