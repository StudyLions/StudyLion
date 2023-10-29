from typing import Optional

import discord

from meta import LionBot
from meta.errors import UserInputError
from utils.lib import replace_multiple
from babel.translator import ctx_translator
from settings import ModelData
from settings.groups import SettingGroup, ModelConfig, SettingDotDict
from settings.setting_types import (
    ChannelSetting, RoleSetting, BoolSetting, StringSetting, IntegerSetting, DurationSetting
)

from .data import TimerData

from . import babel

_p = babel._p


class TimerConfig(ModelConfig):
    settings = SettingDotDict()
    _model_settings = set()
    model = TimerData.Timer


class TimerOptions(SettingGroup):
    @TimerConfig.register_model_setting
    class VoiceChannel(ModelData, ChannelSetting):
        setting_id = 'voice_channel'

        _display_name = _p('timerset:voice_channel', "channel")
        _desc = _p(
            'timerset:voice_channel|desc',
            "Channel in which to track timer members and send alerts."
        )

        _model = TimerData.Timer
        _column = TimerData.Timer.channelid.name
        _create_row = False
        _allow_object = False

    @TimerConfig.register_model_setting
    class NotificationChannel(ModelData, ChannelSetting):
        setting_id = 'notification_channel'

        _display_name = _p('timerset:notification_channel', "notification_channel")
        _desc = _p(
            'timerset:notification_channel|desc',
            "Channel to which to send timer status cards and notifications."
        )

        _model = TimerData.Timer
        _column = TimerData.Timer.notification_channelid.name
        _create_row = False
        _allow_object = False

        @classmethod
        async def _check_value(cls, parent_id: int, value, **kwargs):
            if value is not None:
                # TODO: Check we either have or can create a webhook
                # TODO: Check we can send messages, embeds, and files
                ...

        @classmethod
        def _format_data(cls, parent_id, data, timer=None, **kwargs):
            actual = timer.notification_channel if timer is not None else None
            if data is None and actual is not None:
                t = ctx_translator.get().t
                formatted = t(_p(
                    'timerset:notification_channel|format:notset',
                    "Not Set (Using {channel})"
                )).format(channel=actual.mention)
            else:
                formatted = super()._format_data(parent_id, data, **kwargs)
            return formatted

    @TimerConfig.register_model_setting
    class InactivityThreshold(ModelData, IntegerSetting):
        setting_id = 'inactivity_threshold'

        _display_name = _p('timerset:inactivity_threshold|inactivity_threshold', "inactivity_threshold")
        _desc = _p(
            'timerset:inactivity_threshold|desc',
            "Number of inactive focus+break stages before a member is removed from the timer."
        )
        _accepts = _p(
            'timerset:inactivity_threshold|desc',
            "How many timer cycles before kicking inactive members."
        )
        _model = TimerData.Timer
        _column = TimerData.Timer.inactivity_threshold.name
        _create_row = False

        _min = 0
        _max = 64

        @property
        def input_formatted(self):
            return str(self._data) if self._data is not None else ''

        @classmethod
        async def _parse_string(cls, parent_id, string, **kwargs):
            try:
                return await super()._parse_string(parent_id, string, **kwargs)
            except UserInputError:
                t = ctx_translator.get().t
                raise UserInputError(
                    t(_p(
                        'timerset:inactivity_length|desc',
                        "The inactivity threshold must be a positive whole number!"
                    ))
                )

    @TimerConfig.register_model_setting
    class ManagerRole(ModelData, RoleSetting):
        setting_id = 'manager_role'

        _display_name = _p('timerset:manager_role', "manager_role")
        _desc = _p(
            'timerset:manager_role|desc',
            "Role allowed to start, stop, and edit the focus/break lengths."
        )

        _model = TimerData.Timer
        _column = TimerData.Timer.manager_roleid.name
        _create_row = False
        _allow_object = False

        @classmethod
        def _format_data(cls, parent_id, data, timer=None, **kwargs):
            if data is None:
                t = ctx_translator.get().t
                formatted = t(_p(
                    'timerset:manager_role|format:notset',
                    "Not Set (Only Admins may start/stop or edit pattern)"
                ))
            else:
                formatted = super()._format_data(parent_id, data, **kwargs)
            return formatted

    @TimerConfig.register_model_setting
    class VoiceAlerts(ModelData, BoolSetting):
        setting_id = 'voice_alerts'

        _display_name = _p('timerset:voice_alerts', "voice_alerts")
        _desc = _p(
            'timerset:voice_alerts|desc',
            "Whether to join the voice channel and announce focus and break stages."
        )
        _default = True

        _model = TimerData.Timer
        _column = TimerData.Timer.voice_alerts.name
        _create_row = False

    @TimerConfig.register_model_setting
    class BaseName(ModelData, StringSetting):
        setting_id = 'base_name'

        _display_name = _p('timerset:base_name', "name")
        _desc = _p(
            'timerset:base_name|desc',
            "Timer name, as shown on the timer card."
        )
        _accepts = _p(
            'timerset:base_name|accepts',
            "Any short name, shown on the timer card."
        )

        # TODO: Consider ways of localising string setting defaults?
        # Probably using the default property?
        _default = "Timer"

        _model = TimerData.Timer
        _column = TimerData.Timer.pretty_name.name
        _create_row = False

    @TimerConfig.register_model_setting
    class ChannelFormat(ModelData, StringSetting):
        setting_id = 'channel_name_format'

        _display_name = _p('timerset:channel_name_format', "channel_name")
        _desc = _p(
            'timerset:channel_name_format|desc',
            "Auto-updating voice channel name, accepting {remaining}, {name}, {pattern}, and {stage} keys."
        )
        _accepts = _p(
            'timerset:channel_name|accepts',
            "Timer channel name, with keys {remaining}, {name}, {pattern}, and {stage}."
        )

        _default = "{name} {pattern} - {stage}"

        _model = TimerData.Timer
        _column = TimerData.Timer.channel_name.name
        _create_row = False

        @classmethod
        async def _parse_string(cls, parent_id, string, **kwargs):
            # Enforce a length limit on a test-rendered string.
            # TODO: Localised formatkey transformation
            if string.lower() in ('', 'none', 'default'):
                # Special cases for unsetting
                return None

            testmap = {
                '{remaining}': "10m",
                '{name}': "Longish name",
                '{stage}': "FOCUS",
                '{members}': "25",
                '{pattern}': "50/10",
            }
            testmapped = replace_multiple(string, testmap)
            if len(testmapped) > 100:
                t = ctx_translator.get().t
                raise UserInputError(
                    t(_p(
                        'timerset:channel_name_format|error:too_long',
                        "The provided name is too long! Channel names can be at most `100` characters."
                    ))
                )
            else:
                return string

        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            """
            Overriding format to truncate displayed string.
            """
            if data is not None and len(data) > 100:
                data = data[:97] + '...'
            return super()._format_data(parent_id, data, **kwargs)

    @TimerConfig.register_model_setting
    class FocusLength(ModelData, DurationSetting):
        setting_id = 'focus_length'

        _display_name = _p('timerset:focus_length', "focus_length")
        _desc = _p(
            'timerset:focus_length|desc',
            "Length of the focus stage of the timer in minutes."
        )
        _virtual = True
        _accepts = _p(
            'timerset:focus_length|accepts',
            "A positive integer number of minutes."
        )
        _required = True

        _model = TimerData.Timer
        _column = TimerData.Timer.focus_length.name
        _create_row = False

        _default_multiplier = 60
        allow_zero = False
        _show_days = False

        @property
        def input_formatted(self):
            return str(int(self._data // 60)) if self._data else '25'

        @classmethod
        async def _parse_string(cls, parent_id, string, **kwargs):
            try:
                return await super()._parse_string(parent_id, string, **kwargs)
            except UserInputError:
                t = ctx_translator.get().t
                raise UserInputError(
                    t(_p(
                        'timerset:focus_length|desc',
                        "Please enter a positive number of minutes."
                    ))
                )

    @TimerConfig.register_model_setting
    class BreakLength(ModelData, DurationSetting):
        setting_id = 'break_length'

        _display_name = _p('timerset:break_length', "break_length")
        _desc = _p(
            'timerset:break_length|desc',
            "Length of the break stage of the timer in minutes."
        )
        _virtual = True
        _accepts = _p(
            'timerset:break_length|accepts',
            "A positive integer number of minutes."
        )
        _required = True

        _model = TimerData.Timer
        _column = TimerData.Timer.break_length.name
        _create_row = False

        _default_multiplier = 60
        allow_zero = False
        _show_days = False

        @property
        def input_formatted(self):
            return str(int(self._data // 60)) if self._data else '5'

        @classmethod
        async def _parse_string(cls, parent_id, string, **kwargs):
            try:
                return await super()._parse_string(parent_id, string, **kwargs)
            except UserInputError:
                t = ctx_translator.get().t
                raise UserInputError(
                    t(_p(
                        'timerset:break_length|desc',
                        "Please enter a positive number of minutes."
                    ))
                )
