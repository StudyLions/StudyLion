import discord

from settings import GuildSettings, GuildSetting
import settings


@GuildSettings.attach_setting
class rent_category(settings.Channel, GuildSetting):
    category = "Rented Rooms"

    attr_name = "rent_category"
    _data_column = "renting_category"

    display_name = "rent_category"
    desc = "Category in which members can rent their own study rooms."

    _default = None

    long_desc = (
        "Members can use the `rent` command to "
        "buy the use of a new private voice channel in this category for `24h`."
    )
    _accepts = "A category channel."

    _chan_type = discord.ChannelType.category

    @property
    def success_response(self):
        if self.value:
            return "Members may now rent private voice channels under **{}**.".format(self.value.name)
        else:
            return "Members may no longer rent private voice channels."


@GuildSettings.attach_setting
class rent_member_limit(settings.Integer, GuildSetting):
    category = "Rented Rooms"

    attr_name = "rent_member_limit"
    _data_column = "renting_cap"

    display_name = "rent_member_limit"
    desc = "Maximum number of people that can be added to a rented room."

    _default = 24

    long_desc = (
        "Maximum number of people a member can add to a rented private voice channel."
    )
    _accepts = "An integer number of members."

    @property
    def success_response(self):
        return "Members will now be able to add at most `{}` people to their channel.".format(self.value)


@GuildSettings.attach_setting
class rent_room_price(settings.Integer, GuildSetting):
    category = "Rented Rooms"

    attr_name = "rent_room_price"
    _data_column = "renting_price"

    display_name = "rent_price"
    desc = "Price of a privated voice channel."

    _default = 1000

    long_desc = (
        "How much it costs for a member to rent a private voice channel."
    )
    _accepts = "An integer number of coins."

    @property
    def success_response(self):
        return "Private voice channels now cost `{}` coins.".format(self.value)
