import discord

import settings
from settings import GuildSettings, GuildSetting

from .tracker import AccountabilityGuild as AG


@GuildSettings.attach_setting
class accountability_category(settings.Channel, settings.GuildSetting):
    category = "Accountability Rooms"

    attr_name = "accountability_category"
    _data_column = "accountability_category"

    display_name = "accountability_category"
    desc = "Category in which to make the accountability rooms."

    _default = None

    long_desc = (
        "\"Accountability\" category channel.\n"
        "The accountability voice channels will be created here."
    )
    _accepts = "A category channel."

    _chan_type = discord.ChannelType.category

    @property
    def success_response(self):
        if self.value:
            # TODO Move this somewhere better
            if self.id not in AG.cache:
                AG(self.id)
                return "The accountability category has been changed to **{}**.".format(self.value.name)
            else:
                return "The accountability system has been started in **{}**.".format(self.value.name)
        else:
            if self.id in AG.cache:
                aguild = AG.cache[self.id]
                if aguild.current_slot:
                    aguild.current_lost.cancel()
                if aguild.next_slot:
                    aguild.next_slot.cancel()
                return "The accountability system has been stopped."
            else:
                return "The accountability category has been unset."


@GuildSettings.attach_setting
class accountability_lobby(settings.Channel, settings.GuildSetting):
    category = "Accountability Rooms"

    attr_name = "accountability_lobby"
    _data_column = attr_name

    display_name = attr_name
    desc = "Category in which to post accountability session status updates."

    _default = None

    long_desc = (
        "Accountability session updates will be posted here, and members will be notified in this channel.\n"
        "The channel will be automatically created in the accountability category if it does not exist.\n"
        "Members do not need to be able to write in the channel."
    )
    _accepts = "Any text channel."

    _chan_type = discord.ChannelType.text

    async def auto_create(self):
        # TODO: FUTURE
        ...


@GuildSettings.attach_setting
class accountability_price(settings.Integer, GuildSetting):
    category = "Accountability Rooms"

    attr_name = "accountability_price"
    _data_column = attr_name

    display_name = attr_name
    desc = "Cost of booking an accountability time slot."

    _default = 100

    long_desc = (
        "The price of booking each one hour accountability room slot."
    )
    _accepts = "An integer number of coins."

    @property
    def success_response(self):
        return "Accountability slots now cost `{}` coins.".format(self.value)


@GuildSettings.attach_setting
class accountability_bonus(settings.Integer, GuildSetting):
    category = "Accountability Rooms"

    attr_name = "accountability_bonus"
    _data_column = attr_name

    display_name = attr_name
    desc = "Bonus given when all accountability members attend a time slot."

    _default = 1000

    long_desc = (
        "The extra bonus given when all the members who have booked an accountability time slot attend."
    )
    _accepts = "An integer number of coins."

    @property
    def success_response(self):
        return "Accountability members will now get `{}` coins if everyone joins.".format(self.value)


@GuildSettings.attach_setting
class accountability_reward(settings.Integer, GuildSetting):
    category = "Accountability Rooms"

    attr_name = "accountability_reward"
    _data_column = attr_name

    display_name = attr_name
    desc = "Reward given for attending a booked accountability slot."

    _default = 200

    long_desc = (
        "Amount given to a member who books an accountability slot and attends it."
    )
    _accepts = "An integer number of coins."

    @property
    def success_response(self):
        return "Accountability members will now get `{}` coins at the end of their slot.".format(self.value)
