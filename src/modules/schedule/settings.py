from collections import defaultdict
import discord

from settings import ModelData, ListData
from settings.groups import SettingGroup, ModelConfig, SettingDotDict
from settings.setting_types import (
    ChannelSetting, IntegerSetting, ChannelListSetting, RoleSetting
)
from core.setting_types import CoinSetting
from meta import conf
from meta.errors import UserInputError
from meta.sharding import THIS_SHARD
from meta.logger import log_wrap

from babel.translator import ctx_translator

from . import babel, logger
from .data import ScheduleData

_p = babel._p


class ScheduleConfig(ModelConfig):
    settings = SettingDotDict()
    _model_settings = set()
    model = ScheduleData.ScheduleGuild


class ScheduleSettings(SettingGroup):
    @ScheduleConfig.register_model_setting
    class SessionLobby(ModelData, ChannelSetting):
        setting_id = 'session_lobby'
        _event = 'guildset_session_lobby'
        _set_cmd = 'configure schedule'

        _display_name = _p('guildset:session_lobby', "session_lobby")
        _desc = _p(
            'guildset:session_lobby|desc',
            "Channel to post scheduled session announcement and status to."
        )
        _long_desc = _p(
            'guildset:session_lobby|long_desc',
            "Channel in which to announce scheduled sessions and post their status. "
            "I must have the `MANAGE_WEBHOOKS` permission in this channel.\n"
            "**This must be configured in order for the scheduled session system to function.**"
        )
        _accepts = _p(
            'guildset:session_lobby|accepts',
            "Name or id of the session lobby channel."
        )

        _model = ScheduleData.ScheduleGuild
        _column = ScheduleData.ScheduleGuild.lobby_channel.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            if self.data:
                resp = t(_p(
                    'guildset:session_lobby|set_response|set',
                    "Scheduled sessions will now be announced in {channel}"
                )).format(channel=self.formatted)
            else:
                resp = t(_p(
                    'guildset:session_lobby|set_response|unset',
                    "The schedule session lobby has been unset. Shutting down scheduled session system."
                ))
            return resp

        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            t = ctx_translator.get().t
            if data is None:
                formatted = t(_p(
                    'guildset:session_lobby|formatted|unset',
                    "`Not Set` (The scheduled session system is disabled.)"
                ))
            else:
                formatted = t(_p(
                    'guildset:session_lobby|formatted|set',
                    "<#{channelid}>"
                )).format(channelid=data)
            return formatted

    @ScheduleConfig.register_model_setting
    class SessionRoom(ModelData, ChannelSetting):
        setting_id = 'session_room'
        _set_cmd = 'configure schedule'

        _display_name = _p('guildset:session_room', "session_room")
        _desc = _p(
            'guildset:session_room|desc',
            "Special voice channel open to scheduled session members."
        )
        _long_desc = _p(
            'guildset:session_room|long_desc',
            "If set, this voice channel serves as a dedicated room for scheduled session members. "
            "During (and slightly before) each scheduled session, all members who have booked the session "
            "will be given permission to join the voice channel (via permission overwrites). "
            "I require the `MANAGE_CHANNEL`, `MANAGE_PERMISSIONS`, `CONNECT`, and `VIEW_CHANNEL` permissions "
            "in this channel, and my highest role must be higher than all permission overwrites set in the channel. "
            "Furthermore, if this is set to a *category* channel, then the permission overwrites will apply "
            "to all *synced* channels under the category, as usual."
        )
        _accepts = _p(
            'guildset:session_room|accepts',
            "Name or id of the session room voice channel."
        )
        channel_types = [discord.VoiceChannel, discord.CategoryChannel]

        _model = ScheduleData.ScheduleGuild
        _column = ScheduleData.ScheduleGuild.room_channel.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            if self.data:
                resp = t(_p(
                    'guildset:session_room|set_response|set',
                    "Schedule session members will now be given access to {channel}"
                )).format(channel=self.formatted)
            else:
                resp = t(_p(
                    'guildset:session_room|set_response|unset',
                    "The dedicated schedule session room has been removed."
                ))
            return resp

    class SessionChannels(ListData, ChannelListSetting):
        setting_id = 'session_channels'

        _display_name = _p('guildset:session_channels', "session_channels")
        _desc = _p(
            'guildset:session_channels|desc',
            "Voice channels in which to track activity for scheduled sessions."
        )
        _long_desc = _p(
            'guildset:session_channels|long_desc',
            "Only activity in these channels (and in `session_room` if set) will count towards "
            "scheduled session attendance. If a category is selected, then all channels "
            "under the category will also be included. "
            "Activity tracking also respects the `untracked_voice_channels` setting."
        )
        _accepts = _p(
            'guildset:session_channels|accepts',
            "Comma separated list of session channel names or ids."
        )
        _default = None

        _table_interface = ScheduleData.schedule_channels
        _id_column = 'guildid'
        _data_column = 'channelid'
        _order_column = 'channelid'

        _cache = {}

        @property
        def update_message(self):
            t = ctx_translator.get().t
            if self.data:
                resp = t(_p(
                    'guildset:session_channels|set_response|set',
                    "Activity in the following sessions will now count towards scheduled session attendance: {channels}"
                )).format(channels=self.formatted)
            else:
                resp = t(_p(
                    'guildset:session_channels|set_response|unset',
                    "Activity in all (tracked) voice channels will now count towards session attendance."
                ))
            return resp

        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            t = ctx_translator.get().t
            if data is None:
                formatted = t(_p(
                    'guildset:session_channels|formatted|unset',
                    "All Channels (excluding `untracked_channels`)"
                ))
            else:
                formatted = super()._format_data(parent_id, data, **kwargs)
            return formatted

        @classmethod
        @log_wrap(action='Cache Schedule Channels')
        async def setup(cls, bot):
            """
            Pre-load schedule channels for every guild on the current shard.
            This includes guilds which the client cannot see.
            """
            data = bot.db.registries['ScheduleData']

            rows = await data.schedule_channels.select_where(THIS_SHARD)
            new_cache = defaultdict(list)
            count = 0
            for row in rows:
                new_cache[row['guildid']].append(row['channelid'])
                count += 1
            cls._cache.clear()
            cls._cache.update(new_cache)
            logger.info(f"Loaded {count} schedule session channels on this shard.")

    @ScheduleConfig.register_model_setting
    class ScheduleCost(ModelData, CoinSetting):
        setting_id = 'schedule_cost'
        _set_cmd = 'configure schedule'

        _display_name = _p('guildset:schedule_cost', "schedule_cost")
        _desc = _p(
            'guildset:schedule_cost|desc',
            "Booking cost for each scheduled session."
        )
        _long_desc = _p(
            'guildset:schedule_cost|long_desc',
            "Members will be charged this many LionCoins for each scheduled session they book."
        )
        _accepts = _p(
            'guildset:schedule_cost|accepts',
            "Price of each session booking (non-negative integer)."
        )
        _default = 100

        _model = ScheduleData.ScheduleGuild
        _column = ScheduleData.ScheduleGuild.schedule_cost.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            resp = t(_p(
                'guildset:schedule_cost|set_response',
                "Schedule session bookings will now cost {coin} **{amount}** per timeslot."
            )).format(
                coin=conf.emojis.coin,
                amount=self.value
            )
            return resp

        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            if data is not None:
                t = ctx_translator.get().t
                formatted = t(_p(
                    'guildset:schedule_cost|formatted',
                    "{coin}**{amount}** per booking."
                )).format(coin=conf.emojis.coin, amount=data)
                return formatted

    @ScheduleConfig.register_model_setting
    class AttendanceReward(ModelData, CoinSetting):
        setting_id = 'attendance_reward'
        _set_cmd = 'configure schedule'

        _display_name = _p('guildset:attendance_reward', "attendance_reward")
        _desc = _p(
            'guildset:attendance_reward|desc',
            "Reward for attending a booked scheduled session."
        )
        _long_desc = _p(
            'guildset:attendance_reward|long_desc',
            "When a member successfully attends a scheduled session they booked, "
            "they will be awarded this many LionCoins. "
            "Should generally be more than the `schedule_cost` setting."
        )
        _accepts = _p(
            'guildset:attendance_reward|accepts',
            "Number of coins to reward session attendance."
        )
        _default = 200

        _model = ScheduleData.ScheduleGuild
        _column = ScheduleData.ScheduleGuild.reward.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            resp = t(_p(
                'guildset:attendance_reward|set_response',
                "Members will be rewarded {coin}**{amount}** when they attend a scheduled session."
            )).format(coin=conf.emojis.coin, amount=self.value)
            return resp

        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            if data is not None:
                t = ctx_translator.get().t
                formatted = t(_p(
                    'guildset:attendance_reward|formatted',
                    "{coin}**{amount}** upon attendance."
                )).format(coin=conf.emojis.coin, amount=data)
                return formatted

    @ScheduleConfig.register_model_setting
    class AttendanceBonus(ModelData, CoinSetting):
        setting_id = 'attendance_bonus'
        _set_cmd = 'configure schedule'

        _display_name = _p('guildset:attendance_bonus', "group_attendance_bonus")
        _desc = _p(
            'guildset:attendance_bonus|desc',
            "Bonus reward given when all members attend a scheduled session."
        )
        _long_desc = _p(
            'guildset:attendance_bonus|long_desc',
            "When all members who have booked a session successfully attend the session, "
            "they will be given this bonus in *addition* to the `attendance_reward`."
        )
        _accepts = _p(
            'guildset:attendance_bonus|accepts',
            "Bonus coins rewarded when everyone attends a session."
        )
        _default = 200

        _model = ScheduleData.ScheduleGuild
        _column = ScheduleData.ScheduleGuild.bonus_reward.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            resp = t(_p(
                'guildset:attendance_bonus|set_response',
                "Session members will be rewarded an additional {coin}**{amount}** when everyone attends."
            )).format(coin=conf.emojis.coin, amount=self.value)
            return resp

        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            if data is not None:
                t = ctx_translator.get().t
                formatted = t(_p(
                    'guildset:attendance_bonus|formatted',
                    "{coin}**{amount}** bonus when all booked members attend."
                )).format(coin=conf.emojis.coin, amount=data)
                return formatted

    @ScheduleConfig.register_model_setting
    class MinAttendance(ModelData, IntegerSetting):
        setting_id = 'min_attendance'
        _set_cmd = 'configure schedule'

        _display_name = _p('guildset:min_attendance', "min_attendance")
        _desc = _p(
            'guildset:min_attendance|desc',
            "Minimum attendance before reward eligability."
        )
        _long_desc = _p(
            'guildset:min_attendance|long_desc',
            "Scheduled session members will need to attend the session for at least this number of minutes "
            "before they are marked as having attended (and hence are rewarded)."
        )
        _accepts = _p(
            'guildset:min_attendance|accepts',
            "Number of minutes (1-60) before attendance is counted."
        )
        _default = 10
        _min = 1
        _max = 60

        _model = ScheduleData.ScheduleGuild
        _column = ScheduleData.ScheduleGuild.min_attendance.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            resp = t(_p(
                'guildset:min_attendance|set_response',
                "Members will be rewarded after they have attended booked sessions for at least **`{amount}`** minutes."
            )).format(amount=self.value)
            return resp

        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            if data is not None:
                t = ctx_translator.get().t
                formatted = t(_p(
                    'guildset:min_attendance|formatted',
                    "**`{amount}`** minutes"
                )).format(amount=data)
                return formatted

        @classmethod
        async def _parse_string(cls, parent_id, string: str, **kwargs):
            if not string:
                return None

            string = string.strip('m ')

            num = int(string) if string.isdigit() else None
            try:
                num = int(string)
            except Exception:
                num = None

            if num is None or not 0 < num < 60:
                t = ctx_translator.get().t
                error = t(_p(
                    'guildset:min_attendance|parse|error',
                    "Minimum attendance must be an integer number of minutes between `1` and `60`."
                ))
                raise UserInputError(error)

    @ScheduleConfig.register_model_setting
    class BlacklistRole(ModelData, RoleSetting):
        setting_id = 'schedule_blacklist_role'
        _set_cmd = 'configure schedule'
        _event = 'guildset_schedule_blacklist_role'

        _display_name = _p('guildset:schedule_blacklist_role', "schedule_blacklist_role")
        _desc = _p(
            'guildset:schedule_blacklist_role|desc',
            "Role which disables scheduled session booking."
        )
        _long_desc = _p(
            'guildset:schedule_blacklist_role|long_desc',
            "Members with this role will not be allowed to book scheduled sessions in this server. "
            "If the role is manually added, all future scheduled sessions for the user are cancelled. "
            "This provides a way to stop repeatedly unreliable members from blocking the group bonus for all members. "
            "Alternatively, consider setting the booking cost (and reward) very high to provide "
            "a strong disincentive for not attending a session."
        )
        _accepts = _p(
            'guildset:schedule_blacklist_role|accepts',
            "Blacklist role name or id."
        )

        _model = ScheduleData.ScheduleGuild
        _column = ScheduleData.ScheduleGuild.blacklist_role.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            if self.data:
                resp = t(_p(
                    'guildset:schedule_blacklist_role|set_response|set',
                    "Members with {role} will be unable to book scheduled sessions."
                )).format(role=self.formatted)
            else:
                resp = t(_p(
                    'guildset:schedule_blacklist_role|set_response|unset',
                    "The schedule blacklist role has been unset."
                ))
            return resp

        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            t = ctx_translator.get().t
            if data is not None:
                formatted = t(_p(
                    'guildset:schedule_blacklist_role|formatted|set',
                    "{role} members will not be able to book scheduled sessions."
                )).format(role=f"<&{data}>")
            else:
                formatted = t(_p(
                    'guildset:schedule_blacklist_role|formatted|unset',
                    "Not Set"
                ))
            return formatted

    @ScheduleConfig.register_model_setting
    class BlacklistAfter(ModelData, IntegerSetting):
        setting_id = 'schedule_blacklist_after'
        _set_cmd = 'configure schedule'

        _display_name = _p('guildset:schedule_blacklist_after', "schedule_blacklist_after")
        _desc = _p(
            'guildset:schedule_blacklist_after|desc',
            "Number of missed sessions within 24h before blacklisting."
        )
        _long_desc = _p(
            'guildset:schedule_blacklist_after|long_desc',
            "Members who miss more than this number of booked sessions in a single 24 hour period "
            "will be automatically given the `blacklist_role`. "
            "Has no effect if the `blacklist_role` is not set or if I do not have sufficient permissions "
            "to assign the blacklist role."
        )
        _accepts = _p(
            'guildset:schedule_blacklist_after|accepts',
            "A number of missed sessions (1-24) before blacklisting."
        )
        _default = None
        _min = 1
        _max = 24

        _model = ScheduleData.ScheduleGuild
        _column = ScheduleData.ScheduleGuild.blacklist_after.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            if self.data:
                resp = t(_p(
                    'guildset:schedule_blacklist_after|set_response|set',
                    "Members will be blacklisted after **`{amount}`** missed sessions within `24h`."
                )).format(amount=self.data)
            else:
                resp = t(_p(
                    'guildset:schedule_blacklist_after|set_response|unset',
                    "Members will not be automatically blacklisted from booking scheduled sessions."
                ))
            return resp

        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            t = ctx_translator.get().t
            if data is not None:
                formatted = t(_p(
                    'guildset:schedule_blacklist_after|formatted|set',
                    "Blacklist after **`{amount}`** missed sessions within `24h`."
                )).format(amount=data)
            else:
                formatted = t(_p(
                    'guildset:schedule_blacklist_after|formatted|unset',
                    "Do not automatically blacklist."
                ))
            return formatted

        @classmethod
        async def _parse_string(cls, parent_id, string: str, **kwargs):
            try:
                return await super()._parse_string(parent_id, string, **kwargs)
            except UserInputError:
                t = ctx_translator.get().t
                error = t(_p(
                    'guildset:schedule_blacklist_role|parse|error',
                    "Blacklist threshold must be a number between `1` and `24`."
                ))
                raise UserInputError(error) from None
