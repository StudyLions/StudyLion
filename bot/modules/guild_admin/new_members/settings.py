import datetime
import discord

import settings
from settings import GuildSettings, GuildSetting
import settings.setting_types as stypes
from wards import guild_admin

from .data import autoroles, bot_autoroles


@GuildSettings.attach_setting
class greeting_channel(stypes.Channel, GuildSetting):
    """
    Setting describing the destination of the greeting message.

    Extended to support the following special values, with input and output supported.
        Data `None` corresponds to `Off`.
        Data `1` corresponds to `DM`.
    """
    DMCHANNEL = object()

    category = "New Members"

    attr_name = 'greeting_channel'
    _data_column = 'greeting_channel'

    display_name = "greeting_channel"
    desc = "Channel to send the greeting message in"

    long_desc = (
        "Channel to post the `greeting_message` in when a new user joins the server. "
        "Accepts `DM` to indicate the greeting should be direct messaged to the new member."
    )
    _accepts = (
        "Text Channel name/id/mention, or `DM`, or `None` to disable."
    )
    _chan_type = discord.ChannelType.text

    @classmethod
    def _data_to_value(cls, id, data, **kwargs):
        if data is None:
            return None
        elif data == 1:
            return cls.DMCHANNEL
        else:
            return super()._data_to_value(id, data, **kwargs)

    @classmethod
    def _data_from_value(cls, id, value, **kwargs):
        if value is None:
            return None
        elif value == cls.DMCHANNEL:
            return 1
        else:
            return super()._data_from_value(id, value, **kwargs)

    @classmethod
    async def _parse_userstr(cls, ctx, id, userstr, **kwargs):
        lower = userstr.lower()
        if lower in ('0', 'none', 'off'):
            return None
        elif lower == 'dm':
            return 1
        else:
            return await super()._parse_userstr(ctx, id, userstr, **kwargs)

    @classmethod
    def _format_data(cls, id, data, **kwargs):
        if data is None:
            return "Off"
        elif data == 1:
            return "DM"
        else:
            return "<#{}>".format(data)

    @property
    def success_response(self):
        value = self.value
        if not value:
            return "Greeting messages are disabled."
        elif value == self.DMCHANNEL:
            return "Greeting messages will be sent via direct message."
        else:
            return "Greeting messages will be posted in {}".format(self.formatted)


@GuildSettings.attach_setting
class greeting_message(stypes.Message, GuildSetting):
    category = "New Members"

    attr_name = 'greeting_message'
    _data_column = 'greeting_message'

    display_name = 'greeting_message'
    desc = "Greeting message sent to welcome new members."

    long_desc = (
        "Message to send to the configured `greeting_channel` when a member joins the server for the first time."
    )

    _default = r"""
    {
    "embed": {
    "title": "Welcome!",
    "thumbnail": {"url": "{guild_icon}"},
    "description": "Hi {mention}!\nWelcome to **{guild_name}**! You are the **{member_count}**th member.\nThere are currently **{studying_count}** people studying.\nGood luck and stay productive!",
    "color": 15695665
    }
    }
    """

    _substitution_desc = {
        '{mention}': "Mention the new member.",
        '{user_name}': "Username of the new member.",
        '{user_avatar}': "Avatar of the new member.",
        '{guild_name}': "Name of this server.",
        '{guild_icon}': "Server icon url.",
        '{member_count}': "Number of members in the server.",
        '{studying_count}': "Number of current voice channel members.",
    }

    def substitution_keys(self, ctx, **kwargs):
        return {
            '{mention}': ctx.author.mention,
            '{user_name}': ctx.author.name,
            '{user_avatar}': str(ctx.author.avatar_url),
            '{guild_name}': ctx.guild.name,
            '{guild_icon}': str(ctx.guild.icon_url),
            '{member_count}': str(len(ctx.guild.members)),
            '{studying_count}': str(len([member for ch in ctx.guild.voice_channels for member in ch.members]))
        }

    @property
    def success_response(self):
        return "The greeting message has been set!"


@GuildSettings.attach_setting
class returning_message(stypes.Message, GuildSetting):
    category = "New Members"

    attr_name = 'returning_message'
    _data_column = 'returning_message'

    display_name = 'returning_message'
    desc = "Greeting message sent to returning members."

    long_desc = (
        "Message to send to the configured `greeting_channel` when a member returns to the server."
    )

    _default = r"""
    {
    "embed": {
    "title": "Welcome Back {user_name}!",
    "thumbnail": {"url": "{guild_icon}"},
    "description": "Welcome back to **{guild_name}**!\nYou last studied with us <t:{last_time}:R>.\nThere are currently **{studying_count}** people studying.\nGood luck and stay productive!",
    "color": 15695665
    }
    }
    """

    _substitution_desc = {
        '{mention}': "Mention the returning member.",
        '{user_name}': "Username of the member.",
        '{user_avatar}': "Avatar of the member.",
        '{guild_name}': "Name of this server.",
        '{guild_icon}': "Server icon url.",
        '{member_count}': "Number of members in the server.",
        '{studying_count}': "Number of current voice channel members.",
        '{last_time}': "Unix timestamp of the last time the member studied.",
    }

    def substitution_keys(self, ctx, **kwargs):
        return {
            '{mention}': ctx.author.mention,
            '{user_name}': ctx.author.name,
            '{user_avatar}': str(ctx.author.avatar_url),
            '{guild_name}': ctx.guild.name,
            '{guild_icon}': str(ctx.guild.icon_url),
            '{member_count}': str(len(ctx.guild.members)),
            '{studying_count}': str(len([member for ch in ctx.guild.voice_channels for member in ch.members])),
            '{last_time}': int(ctx.alion.data._timestamp.replace(tzinfo=datetime.timezone.utc).timestamp()),
        }

    @property
    def success_response(self):
        return "The returning message has been set!"


@GuildSettings.attach_setting
class starting_funds(stypes.Integer, GuildSetting):
    category = "New Members"

    attr_name = 'starting_funds'
    _data_column = 'starting_funds'

    display_name = 'starting_funds'
    desc = "Coins given when a user first joins."

    long_desc = (
        "Members will be given this number of coins the first time they join the server."
    )

    _default = 0

    @property
    def success_response(self):
        return "Members will be given `{}` coins when they first join the server.".format(self.formatted)


@GuildSettings.attach_setting
class autoroles(stypes.RoleList, settings.ListData, settings.Setting):
    category = "New Members"
    write_ward = guild_admin

    attr_name = 'autoroles'

    _table_interface = autoroles
    _id_column = 'guildid'
    _data_column = 'roleid'

    display_name = "autoroles"
    desc = "Roles to give automatically to new members."

    _force_unique = True

    long_desc = (
        "These roles will be given automatically to users when they join the server. "
        "If `role_persistence` is enabled, the roles will only be given the first time a user joins the server."
    )

    # Flat cache, no need to expire
    _cache = {}

    @property
    def success_response(self):
        if self.value:
            return "New members will be given the following roles:\n{}".format(self.formatted)
        else:
            return "New members will not automatically be given any roles."


@GuildSettings.attach_setting
class bot_autoroles(stypes.RoleList, settings.ListData, settings.Setting):
    category = "New Members"
    write_ward = guild_admin

    attr_name = 'bot_autoroles'

    _table_interface = bot_autoroles
    _id_column = 'guildid'
    _data_column = 'roleid'

    display_name = "bot_autoroles"
    desc = "Roles to give automatically to new bots."

    _force_unique = True

    long_desc = (
        "These roles will be given automatically to bots when they join the server. "
        "If `role_persistence` is enabled, the roles will only be given the first time a bot joins the server."
    )

    # Flat cache, no need to expire
    _cache = {}

    @property
    def success_response(self):
        if self.value:
            return "New bots will be given the following roles:\n{}".format(self.formatted)
        else:
            return "New bots will not automatically be given any roles."


@GuildSettings.attach_setting
class role_persistence(stypes.Boolean, GuildSetting):
    category = "New Members"

    attr_name = "role_persistence"

    _data_column = 'persist_roles'

    display_name = "role_persistence"
    desc = "Whether to remember member roles when they leave the server."
    _outputs = {True: "Enabled", False: "Disabled"}
    _default = True

    long_desc = (
        "When enabled, restores member roles when they rejoin the server.\n"
        "This enables profile roles and purchased roles, such as field of study and colour roles, "
        "as well as moderation roles, "
        "such as the studyban and mute roles, to persist even when a member leaves and rejoins.\n"
        "Note: Members who leave while this is disabled will not have their roles restored."
    )

    @property
    def success_response(self):
        if self.value:
            return "Roles will now be restored when a member rejoins."
        else:
            return "Member roles will no longer be saved or restored."
