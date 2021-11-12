import datetime
import asyncio
import discord

import settings
from utils.lib import DotDict
from utils import seekers  # noqa

from wards import guild_admin
from data import tables as tb


class GuildSettings(settings.ObjectSettings):
    settings = DotDict()


class GuildSetting(settings.ColumnData, settings.Setting):
    _table_interface = tb.guild_config
    _id_column = 'guildid'
    _create_row = True

    category = None

    write_ward = guild_admin


@GuildSettings.attach_setting
class event_log(settings.Channel, GuildSetting):
    category = "Meta"

    attr_name = 'event_log'
    _data_column = 'event_log_channel'

    display_name = "event_log"
    desc = "Bot event logging channel."

    long_desc = (
        "Channel to post 'events', such as workouts completing or members renting a room."
    )

    _chan_type = discord.ChannelType.text

    @property
    def success_response(self):
        if self.value:
            return "The event log is now {}.".format(self.formatted)
        else:
            return "The event log has been unset."

    def log(self, description="", colour=discord.Color.orange(), **kwargs):
        channel = self.value
        if channel:
            embed = discord.Embed(
                description=description,
                colour=colour,
                timestamp=datetime.datetime.utcnow(),
                **kwargs
            )
            asyncio.create_task(channel.send(embed=embed))


@GuildSettings.attach_setting
class admin_role(settings.Role, GuildSetting):
    category = "Guild Roles"

    attr_name = 'admin_role'
    _data_column = 'admin_role'

    display_name = "admin_role"
    desc = "Server administrator role."

    long_desc = (
        "Server administrator role.\n"
        "Allows usage of the administrative commands, such as `config`.\n"
        "These commands may also be used by anyone with the discord adminitrator permission."
    )
    # TODO Expand on what these are.

    @property
    def success_response(self):
        if self.value:
            return "The administrator role is now {}.".format(self.formatted)
        else:
            return "The administrator role has been unset."


@GuildSettings.attach_setting
class mod_role(settings.Role, GuildSetting):
    category = "Guild Roles"

    attr_name = 'mod_role'
    _data_column = 'mod_role'

    display_name = "mod_role"
    desc = "Server moderator role."

    long_desc = (
        "Server moderator role.\n"
        "Allows usage of the modistrative commands."
    )
    # TODO Expand on what these are.

    @property
    def success_response(self):
        if self.value:
            return "The moderator role is now {}.".format(self.formatted)
        else:
            return "The moderator role has been unset."


@GuildSettings.attach_setting
class unranked_roles(settings.RoleList, settings.ListData, settings.Setting):
    category = "Guild Roles"

    attr_name = 'unranked_roles'

    _table_interface = tb.unranked_roles
    _id_column = 'guildid'
    _data_column = 'roleid'

    write_ward = guild_admin
    display_name = "unranked_roles"
    desc = "Roles to exclude from the leaderboards."

    _force_unique = True

    long_desc = (
        "Roles to be excluded from the `top` and `topcoins` leaderboards."
    )

    # Flat cache, no need to expire objects
    _cache = {}

    @property
    def success_response(self):
        if self.value:
            return "The following roles will be excluded from the leaderboard:\n{}".format(self.formatted)
        else:
            return "The excluded roles have been removed."


@GuildSettings.attach_setting
class donator_roles(settings.RoleList, settings.ListData, settings.Setting):
    category = "Hidden"

    attr_name = 'donator_roles'

    _table_interface = tb.donator_roles
    _id_column = 'guildid'
    _data_column = 'roleid'

    write_ward = guild_admin
    display_name = "donator_roles"
    desc = "Donator badge roles."

    _force_unique = True

    long_desc = (
        "Members with these roles will be considered donators and have access to premium features."
    )

    # Flat cache, no need to expire objects
    _cache = {}

    @property
    def success_response(self):
        if self.value:
            return "The donator badges are now:\n{}".format(self.formatted)
        else:
            return "The donator badges have been removed."


@GuildSettings.attach_setting
class alert_channel(settings.Channel, GuildSetting):
    category = "Meta"

    attr_name = 'alert_channel'
    _data_column = 'alert_channel'

    display_name = "alert_channel"
    desc = "Channel to display global user alerts."

    long_desc = (
        "This channel will be used for group notifications, "
        "for example group timers and anti-cheat messages, "
        "as well as for critical alerts to users that have their direct messages disapbled.\n"
        "It should be visible to all members."
    )

    _chan_type = discord.ChannelType.text

    @property
    def success_response(self):
        if self.value:
            return "The alert channel is now {}.".format(self.formatted)
        else:
            return "The alert channel has been unset."

@GuildSettings.attach_setting
class coin_alert_channel(settings.Channel, GuildSetting):
    category = "Meta"

    attr_name = 'coin_alert_channel'
    _data_column = 'coin_alert_channel'

    display_name = "coin_alert_channel"
    desc = "Channel to display information when a user receives some coins."

    long_desc = (
        "Channel to post reasons, when, how many and why when a user receives coins."
    )

    _chan_type = discord.ChannelType.text

    @property
    def success_response(self):
        if self.value:
            return "The coin alert channel is now {}.".format(self.formatted)
        else:
            return "The coin alert channel has been unset."

    def log(self, description="", colour=discord.Color.orange(), **kwargs):
        channel = self.value
        if channel:
            embed = discord.Embed(
                description=description,
                colour=colour,
                timestamp=datetime.datetime.utcnow(),
                **kwargs
            )
            asyncio.create_task(channel.send(embed=embed))