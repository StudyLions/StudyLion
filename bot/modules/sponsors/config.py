from cmdClient.checks import is_owner

from settings import AppSettings, Setting, KeyValueData, ListData
from settings.setting_types import Message, String

from meta import client
from core.data import app_config


@AppSettings.attach_setting
class sponsor_prompt(String, KeyValueData, Setting):
    attr_name = 'sponsor_prompt'
    _default = None

    write_ward = is_owner

    display_name = 'sponsor_prompt'
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


@AppSettings.attach_setting
class sponsor_message(Message, KeyValueData, Setting):
    attr_name = 'sponsor_message'
    _default = '{"content": "Coming Soon!"}'

    write_ward = is_owner

    display_name = 'sponsor_message'
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
