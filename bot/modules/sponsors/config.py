from cmdClient.checks import is_owner

from settings.base import Setting, ColumnData, ObjectSettings
from settings.setting_types import Message, String

from meta import client
from utils.lib import DotDict

from .data import sponsor_text


class SponsorSettings(ObjectSettings):
    settings = DotDict()
    pass


@SponsorSettings.attach_setting
class sponsor_prompt(String, ColumnData, Setting):
    attr_name = 'sponsor_prompt'
    _default = "Type {prefix}sponsors to check our wonderful partners!"

    write_ward = is_owner

    display_name = 'sponsor_prompt'
    desc = "Text to send after core commands to encourage checking `sponsors`."
    long_desc = (
        "Text posted after several commands to encourage users to check the `sponsors` command. "
        "Occurences of `{{prefix}}` will be replaced by the bot prefix."
    )

    _quote = False

    _data_column = 'prompt_text'
    _table_interface = sponsor_text
    _id_column = 'ID'
    _upsert = True
    _create_row = True

    @classmethod
    def _data_to_value(cls, id, data, **kwargs):
        if data:
            return data.replace("{prefix}", client.prefix)
        else:
            return None


@SponsorSettings.attach_setting
class sponsor_message(Message, ColumnData, Setting):
    attr_name = 'sponsor_message'
    _default = '{"content": "Coming Soon!"}'

    write_ward = is_owner

    display_name = 'sponsor_message'
    desc = "`sponsors` command response."

    long_desc = (
        "Message to reply with when a user runs the `sponsors` command."
    )

    _data_column = 'command_response'
    _table_interface = sponsor_text
    _id_column = 'ID'
    _upsert = True
    _create_row = True

    _cmd_str = "{prefix}sponsors --edit"


settings = SponsorSettings(0)
