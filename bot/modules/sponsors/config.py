from cmdClient.checks import is_owner

from settings import AppSettings, Setting, KeyValueData, ListData
from settings.setting_types import Message, String, GuildIDList

from meta import client
from core.data import app_config

from .data import guild_whitelist

@AppSettings.attach_setting
class sponsor_prompt(String, KeyValueData, Setting):
    attr_name = 'sponsor_prompt'
    _default = None

    write_ward = is_owner

    display_name = 'sponsor_prompt'
    category = 'Sponsors'
    desc = "Text to send after core commands to encourage checking `sponsors`."
    long_desc = (
        "Text posted after several commands to encourage users to check the `sponsors` command. "
        "Occurences of `{{prefix}}` will be replaced by the bot prefix."
    )

    _quote = False

    _table_interface = app_config
    _id_column = 'appid'
    _key_column = 'key'
    _value_column = 'value'
    _key = 'sponsor_prompt'

    @classmethod
    def _data_to_value(cls, id, data, **kwargs):
        if data:
            return data.replace("{prefix}", client.prefix)
        else:
            return None

    @property
    def success_response(self):
        if self.value:
            return "The sponsor prompt has been update."
        else:
            return "The sponsor prompt has been cleared."


@AppSettings.attach_setting
class sponsor_message(Message, KeyValueData, Setting):
    attr_name = 'sponsor_message'
    _default = '{"content": "Coming Soon!"}'

    write_ward = is_owner

    display_name = 'sponsor_message'
    category = 'Sponsors'
    desc = "`sponsors` command response."

    long_desc = (
        "Message to reply with when a user runs the `sponsors` command."
    )

    _table_interface = app_config
    _id_column = 'appid'
    _key_column = 'key'
    _value_column = 'value'
    _key = 'sponsor_message'

    _cmd_str = "{prefix}sponsors --edit"

    @property
    def success_response(self):
        return "The `sponsors` command message has been updated."


@AppSettings.attach_setting
class sponsor_guild_whitelist(GuildIDList, ListData, Setting):
    attr_name = 'sponsor_guild_whitelist'
    write_ward = is_owner

    category = 'Sponsors'
    display_name = 'sponsor_hidden_in'
    desc = "Guilds where the sponsor prompt is not displayed."
    long_desc = (
        "A list of guilds where the sponsor prompt hint will be hidden (see the `sponsor_prompt` setting)."
    )

    _table_interface = guild_whitelist
    _id_column = 'appid'
    _data_column = 'guildid'
    _force_unique = True
