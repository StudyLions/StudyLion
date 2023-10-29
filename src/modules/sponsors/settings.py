from settings.data import ListData, ModelData
from settings.groups import SettingGroup
from settings.setting_types import GuildIDListSetting

from core.setting_types import MessageSetting
from core.data import CoreData
from wards import sys_admin_iward
from . import babel
from .data import SponsorData

_p = babel._p


class SponsorSettings(SettingGroup):
    class Whitelist(ListData, GuildIDListSetting):
        setting_id = 'sponsor_whitelist'
        _write_ward = sys_admin_iward

        _display_name = _p(
            'botset:sponsor_whitelist', "sponsor_whitelist"
        )
        _desc = _p(
            'botset:sponsor_whitelist|desc',
            "List of guildids where the sponsor prompt is not shown."
        )
        _long_desc = _p(
            'botset:sponsor_whitelist|long_desc',
            "The sponsor prompt will not appear in the set guilds."
        )
        _accepts = _p(
            'botset:sponsor_whitelist|accetps',
            "Comma separated list of guildids."
        )

        _table_interface = SponsorData.sponsor_whitelist
        _id_column = 'appid'
        _data_column = 'guildid'
        _order_column = 'guildid'

    class SponsorPrompt(ModelData, MessageSetting):
        setting_id = 'sponsor_prompt'
        _set_cmd = 'leo sponsors'
        _write_ward = sys_admin_iward

        _display_name = _p(
            'botset:sponsor_prompt', "sponsor_prompt"
        )
        _desc = _p(
            'botset:sponsor_prompt|desc',
            "Message to add underneath core commands."
        )
        _long_desc = _p(
            'botset:sponsor_prompt|long_desc',
            "Content of the message to send after core commands such as stats,"
            " reminding users to check the sponsors command."
        )

        _model = CoreData.BotConfig
        _column = CoreData.BotConfig.sponsor_prompt.name

        async def editor_callback(self, editor_data):
            self.value = editor_data
            await self.write()

    class SponsorMessage(ModelData, MessageSetting):
        setting_id = 'sponsor_message'
        _set_cmd = 'leo sponsors'
        _write_ward = sys_admin_iward

        _display_name = _p(
            'botset:sponsor_message', "sponsor_message"
        )
        _desc = _p(
            'botset:sponsor_message|desc',
            "Message to send in response to /sponsors command."
        )
        _long_desc = _p(
            'botset:sponsor_message|long_desc',
            "Content of the message to send when a user runs the `/sponsors` command."
        )

        _model = CoreData.BotConfig
        _column = CoreData.BotConfig.sponsor_message.name

        async def editor_callback(self, editor_data):
            self.value = editor_data
            await self.write()
