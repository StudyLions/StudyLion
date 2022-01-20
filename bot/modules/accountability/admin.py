import asyncio
import discord

import settings
from settings import GuildSettings, GuildSetting

from .tracker import AccountabilityGuild as AG


@GuildSettings.attach_setting
class accountability_category(settings.Channel, settings.GuildSetting):
    category = "Scheduled Sessions"

    attr_name = "accountability_category"
    _data_column = "accountability_category"

    display_name = "session_category"
    desc = "Category in which to make the scheduled session rooms."

    _default = None

    long_desc = (
        "\"Schedule session\" category channel.\n"
        "Scheduled sessions will be held in voice channels created under this category."
    )
    _accepts = "A category channel."

    _chan_type = discord.ChannelType.category

    @property
    def success_response(self):
        if self.value:
            # TODO Move this somewhere better
            if self.id not in AG.cache:
                AG(self.id)
                return "The session category has been changed to **{}**.".format(self.value.name)
            else:
                return "The scheduled session system has been started in **{}**.".format(self.value.name)
        else:
            if self.id in AG.cache:
                aguild = AG.cache.pop(self.id)
                if aguild.current_slot:
                    asyncio.create_task(aguild.current_slot.cancel())
                if aguild.upcoming_slot:
                    asyncio.create_task(aguild.upcoming_slot.cancel())
                return "The scheduled session system has been shut down."
            else:
                return "The scheduled session category has been unset."


@GuildSettings.attach_setting
class accountability_lobby(settings.Channel, settings.GuildSetting):
    category = "Scheduled Sessions"

    attr_name = "accountability_lobby"
    _data_column = attr_name

    display_name = "session_lobby"
    desc = "Category in which to post scheduled session notifications updates."

    _default = None

    long_desc = (
        "Scheduled session updates will be posted here, and members will be notified in this channel.\n"
        "The channel will be automatically created in the configured `session_category` if it does not exist.\n"
        "Members do not need to be able to write in the channel."
    )
    _accepts = "Any text channel."

    _chan_type = discord.ChannelType.text

    async def auto_create(self):
        # TODO: FUTURE
        ...


@GuildSettings.attach_setting
class accountability_price(settings.Integer, GuildSetting):
    category = "Scheduled Sessions"

    attr_name = "accountability_price"
    _data_column = attr_name

    display_name = "session_price"
    desc = "Cost of booking a scheduled session."

    _default = 100

    long_desc = (
        "The price of booking each one hour scheduled session slot."
    )
    _accepts = "An integer number of coins."

    @property
    def success_response(self):
        return "Scheduled session slots now cost `{}` coins.".format(self.value)


@GuildSettings.attach_setting
class accountability_bonus(settings.Integer, GuildSetting):
    category = "Scheduled Sessions"

    attr_name = "accountability_bonus"
    _data_column = attr_name

    display_name = "session_bonus"
    desc = "Bonus given when everyone attends a scheduled session slot."

    _default = 1000

    long_desc = (
        "The extra bonus given to each scheduled session member when everyone who booked attended the session."
    )
    _accepts = "An integer number of coins."

    @property
    def success_response(self):
        return "Scheduled session members will now get `{}` coins if everyone joins.".format(self.value)


@GuildSettings.attach_setting
class accountability_reward(settings.Integer, GuildSetting):
    category = "Scheduled Sessions"

    attr_name = "accountability_reward"
    _data_column = attr_name

    display_name = "session_reward"
    desc = "The individual reward given when a member attends their booked scheduled session."

    _default = 200

    long_desc = (
        "Reward given to a member who attends a booked scheduled session."
    )
    _accepts = "An integer number of coins."

    @property
    def success_response(self):
        return "Members will now get `{}` coins when they attend their scheduled session.".format(self.value)
