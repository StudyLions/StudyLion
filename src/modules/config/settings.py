from typing import Optional
import discord

from settings import ModelData
from settings.setting_types import TimezoneSetting, ChannelSetting
from settings.groups import SettingGroup

from meta.context import ctx_bot
from meta.errors import UserInputError
from core.data import CoreData
from babel.translator import ctx_translator
from wards import low_management_iward

from . import babel

_p = babel._p


class GeneralSettings(SettingGroup):
    class Timezone(ModelData, TimezoneSetting):
        """
        Guild timezone configuration.

        Exposed via `/config general timezone:`, and the standard interface.
        The `timezone` setting acts as the default timezone for all members,
        and the timezone used to display guild-wide statistics.
        """
        setting_id = 'timezone'
        _event = 'guildset_timezone'
        _set_cmd = 'config general'
        _write_ward = low_management_iward

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

    class EventLog(ModelData, ChannelSetting):
        """
        Guild event log channel.
        """
        setting_id = 'eventlog'
        _event = 'guildset_eventlog'
        _set_cmd = 'config general'
        _write_ward = low_management_iward

        _display_name = _p('guildset:eventlog', "event_log")
        _desc = _p(
            'guildset:eventlog|desc',
            "My audit log channel where I send server actions and events (e.g. rankgs and expiring roles)."
        )
        _long_desc = _p(
            'guildset:eventlog|long_desc',
            "If configured, I will log most significant actions taken "
            "or events which occur through my interface, into this channel. "
            "Logged events include, for example:\n"
            "- Member voice activity\n"
            "- Roles equipped and expiring from rolemenus\n"
            "- Privated rooms rented and expiring\n"
            "- Activity ranks earned\n"
            "I must have the 'Manage Webhooks' permission in this channel."
        )

        _model = CoreData.Guild
        _column = CoreData.Guild.event_log_channel.name


        @classmethod
        async def _check_value(cls, parent_id: int, value: Optional[discord.abc.GuildChannel], **kwargs):
            if value is not None:
                t = ctx_translator.get().t
                if not value.permissions_for(value.guild.me).manage_webhooks:
                    raise UserInputError(
                        t(_p(
                            'guildset:eventlog|check_value|error:perms|perm:manage_webhooks',
                            "Cannot set {channel} as an event log! I lack the 'Manage Webhooks' permission there."
                        )).format(channel=value)
                    )

        @property
        def update_message(self):
            t = ctx_translator.get().t
            channel = self.value
            if channel is not None:
                response = t(_p(
                    'guildset:eventlog|response|set',
                    "Events will now be logged to {channel}"
                )).format(channel=channel.mention)
            else:
                response = t(_p(
                    'guildset:eventlog|response|unset',
                    "Guild events will no longer be logged."
                ))
            return response
