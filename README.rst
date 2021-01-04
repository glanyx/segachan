Who Is SegaChan?
===================

Overview
--------

SegaChan is a Discord Bot forked from Sweeper Bot. This is a privately used bot by the `Sega Forever Discord server <https://discord.gg/segaforever>`. She handles a lot of functions for us, mostly in the space of moderation tools, including but not limited to:

- Notes, Warnings, Mutes, and Banning.
- Logging of deleted messages, reactions, voice activity, member joins/parts, and name changes.
- AntiSpam features including auto muting those sending too many messages too quickly.
- Reaction based role assignment.
- Request creation with voting reactions.
- Mod Mail which allows users to send the bot a message and have it relayed to our mods and allows our mods to respond.

Original Version
----------------

The original version that this bot is forked from can be found `here <https://bitbucket.org/layer7solutions/sweeperbot/src/python-rewrite/>`.

Building The Bot
-----------------

To build the bot the following requirements must be satisfied:

- Python 3.7
- pipenv
- Redis
- PostgreSQL (10-11 tested)
- Sentry.io for error reporting

Installing the bot:

- At the root of the project run ``pipenv install --verbose --skip-lock -e .`` which will install all the packages needed.
- Change directories (cd) into the 'sweeperbot' subdirectory and run ``pipenv run python3 launch.py``
- Congrats, the bot is now running.

Additional notes:

- If a table does not exist, the bot will create the entire table for you. If the table exists and modifications are made then you'll need to manually update the table in the database.
- The bot follows the mentality that the only configuration file should be botconfig.ini and any data is either stored in the redis cache or the database. This allows for the bot to be destroyed and rebuilt without fear of data loss such as during auto deployments on version updates using Bamboo.
