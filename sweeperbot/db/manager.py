"""This module handles the management of the database"""
import configparser

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sweeperbot.db import models


class DatabaseManager:
    def __init__(self, botconfig):
        self.botconfig = botconfig
        self.ENGINE = {}
        self.sessionmaker_dict = {}

    def make_sessionmaker(self, db_config="Database"):
        uname = self.botconfig.get(db_config, "USERNAME")
        pword = self.botconfig.get(db_config, "PASSWORD")
        host = self.botconfig.get(db_config, "HOST")
        port = self.botconfig.get(db_config, "PORT")
        database = self.botconfig.get(db_config, "DATABASE")
        create_metadata_tables = False
        # Set whether to create missing database tables
        try:
            create_metadata_tables = self.botconfig.getboolean(
                db_config, "CREATE_TABLES"
            )
        except configparser.NoOptionError:
            create_metadata_tables = False

        # Set max pool size
        try:
            pool_size = int(self.botconfig.get(db_config, "POOL_SIZE"))
        except configparser.NoOptionError:
            pool_size = 50
        # Set max overflow size
        try:
            max_overflow = int(self.botconfig.get(db_config, "MAX_OVERFLOW"))
        except configparser.NoOptionError:
            max_overflow = 150

        # If the Database isn't in the Engine, create it
        if db_config not in self.ENGINE:
            # Create the Engine
            self.ENGINE[db_config] = create_engine(
                f"postgresql://{uname}:{pword}@{host}:{port}/{database}",
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_timeout=60,
                echo_pool=True,
                pool_pre_ping=True,
                # echo=True,
                # isolation_level="AUTOCOMMIT",
            )

        # If the database session isn't in the sessionmaker dict, create one
        if db_config not in self.sessionmaker_dict:
            # If set to, create the tables
            if create_metadata_tables:
                models.Base.metadata.create_all(self.ENGINE[db_config])
            self.sessionmaker_dict[db_config] = sessionmaker(
                bind=self.ENGINE[db_config], expire_on_commit=False
            )

    def get_session(self, db_config="Database"):
        """Get the session if it exists, otherwise create it"""
        # If the DB is not in the sessionmaker_dict, make it
        if db_config not in self.sessionmaker_dict:
            self.make_sessionmaker(db_config)

        # Get the sessionmaker object from the sessionmaker dict
        sessionmaker_obj = self.sessionmaker_dict[db_config]
        # Get a session from the sessionmaker
        session = sessionmaker_obj()

        return session

    def close_engine(self, db_config="Database"):
        try:
            for db_engine in self.ENGINE:
                db_engine.dispose()
        except Exception as err:
            print(f"Error disposing of Engine for DB: {db_config}. Error: {err}")
