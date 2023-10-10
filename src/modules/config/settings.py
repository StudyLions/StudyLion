from settings import ModelData
from settings.setting_types import TimezoneSetting, ChannelSetting
from settings.groups import SettingGroup

from core.data import CoreData
from babel.translator import ctx_translator

from . import babel

_p = babel._p


class GeneralSettings(SettingGroup):
    class Timezone(ModelData, TimezoneSetting):
        """
        Guild timezone configuration.

        Exposed via `/configure general timezone:`, and the standard interface.
        The `timezone` setting acts as the default timezone for all members,
        and the timezone used to display guild-wide statistics.
        """
        setting_id = 'timezone'
        _event = 'guild_setting_update_timezone'

        _display_name = _p('guildset:timezone', "timezone")
        _desc = _p(
            'guildset:timezone|desc',
            "Guild timezone for statistics display."
        )
        _long_desc = _p(
            'guildset:timezone|long_desc',
            "Guild-wide timezone. "
            "Used to determine start of the day for the leaderboards, "
            "and as the default statistics timezone for members who have not set one."
        )
        _default = 'UTC'

        _model = CoreData.Guild
        _column = CoreData.Guild.timezone.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            return t(_p(
                'guildset:timezone|response',
                "The guild timezone has been set to `{timezone}`."
            )).format(timezone=self.data)

        @property
        def set_str(self):
            bot = ctx_bot.get()
            return bot.core.mention_cmd('configure general') if bot else None

    class EventLog(ModelData, ChannelSetting):
        """
        Guild event log channel.
        """
        setting_id = 'eventlog'
        _event = 'guildset_eventlog'

        _display_name = _p('guildset:eventlog', "event_log")
        _desc = _p(
            'guildset:eventlog|desc',
            "Channel to which to log server events, such as voice sessions and equipped roles."
        )
        # TODO: Reword
        _long_desc = _p(
            'guildset:eventlog|long_desc',
            "An audit log for my own systems, "
            "I will send most significant actions and events that occur through my interface "
            "to this channel. For example, this includes:\n"
            "- Member voice activity\n"
            "- Roles equipped and expiring from rolemenus\n"
            "- Privated rooms rented and expiring\n"
            "- Activity ranks earned\n"
            "I must have the 'Manage Webhooks' permission in this channel."
        )

        # TODO: Updatestr
