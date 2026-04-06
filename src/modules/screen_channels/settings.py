# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-31
# Purpose: Settings for screen share enforcement module
#          (mirrors video_channels/settings.py)
# ============================================================
from cachetools import LRUCache
from collections import defaultdict

from settings import ModelData, ListData
from settings.groups import SettingGroup
from settings.ui import InteractiveSetting
from settings.setting_types import (
    DurationSetting, RoleSetting, RoleListSetting, ChannelListSetting,
    ListSetting
)

from meta import conf
from meta.sharding import THIS_SHARD
from meta.logger import log_wrap
from core.data import CoreData
from babel.translator import ctx_translator
from wards import low_management_iward, high_management_iward

from . import babel, logger
from .data import ScreenData

_p = babel._p


class ScreenSettings(SettingGroup):
    class ScreenChannels(ListData, ChannelListSetting):
        setting_id = "screen_channels"
        _event = 'guildset_screen_channels'
        _write_ward = high_management_iward

        _display_name = _p('guildset:screen_channels', "screen_channels")
        _desc = _p(
            'guildset:screen_channels|desc',
            "List of voice channels and categories in which to enforce screen sharing."
        )
        _long_desc = _p(
            'guildset:screen_channels|long_desc',
            "Members will be required to share their screen in these channels.\n"
            "If they do not enable screen sharing within `15` seconds of joining, "
            "they will be asked to enable it "
            "through a notification in direct messages or the `alert_channel`. "
            "If they still have not enabled it after the `screen_grace_period` has passed, "
            "they will be kicked from the channel. "
            "Further, after the first offence (which is considered a warning), "
            "they will be given the `screen_blacklist` role, if configured, "
            "which will stop them from joining screen share channels.\n"
            "As usual, if a category is configured, this will apply to all voice channels "
            "under the category."
        )
        _accepts = _p(
            'guildset:screen_channels|accepts',
            "Comma separated channel ids or names."
        )

        _cache = LRUCache(maxsize=2500)

        _table_interface = ScreenData.screen_channels
        _id_column = 'guildid'
        _data_column = 'channelid'
        _order_column = 'channelid'

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'guildset:screen_channels|set_response:set',
                    "Members will be asked to share their screen in the following channels: {channels}"
                )).format(channels=self.formatted)
            else:
                resp = t(_p(
                    'guildset:screen_channels|set_response:unset',
                    "Members will not be asked to share their screen in any channels."
                ))
            return resp

        @classmethod
        @log_wrap(action="Cache screen_channels")
        async def setup(cls, bot):
            data: ScreenData = bot.db.registries[ScreenData._name]
            if bot.is_ready():
                rows = await data.screen_channels.select_where(
                    guildid=[guild.id for guild in bot.guilds]
                )
            else:
                rows = await data.screen_channels.select_where(THIS_SHARD)
            new_cache = defaultdict(list)
            count = 0
            for row in rows:
                new_cache[row['guildid']].append(row['channelid'])
                count += 1
            if cls._cache is None:
                cls._cache = LRUCache(2500)
            cls._cache.clear()
            cls._cache.update(new_cache)
            logger.info(f"Loaded {count} screen channels on this shard.")

    class ScreenBlacklist(ModelData, RoleSetting):
        setting_id = "screen_blacklist"
        _event = 'guildset_screen_blacklist'
        _write_ward = high_management_iward

        _display_name = _p('guildset:screen_blacklist', "screen_blacklist")
        _desc = _p(
            'guildset:screen_blacklist|desc',
            "Role given when members are blacklisted from screen share channels."
        )
        _long_desc = _p(
            'guildset:screen_blacklist|long_desc',
            "This role will be automatically given after a member has failed to keep their screen "
            "shared in a screen share channel (see above).\n"
            "Members who have this role will not be able to join configured screen share channels. "
            "The role permissions may be freely configured by server admins "
            "to place further restrictions on the offender.\n"
            "The role may also be manually assigned, to the same effect.\n"
            "If this role is not set, no screen share blacklist will occur, "
            "and members will only be kicked from the channel and warned."
        )
        _accepts = _p(
            'guildset:screen_blacklist|accepts',
            "Blacklist role name or id."
        )
        _default = None

        _model = CoreData.Guild
        _column = CoreData.Guild.screenban_role.name
        _allow_object = False

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'guildset:screen_blacklist|set_response:set',
                    "Members who fail to keep their screen shared will be given {role}"
                )).format(role=f"<@&{self.data}>")
            else:
                resp = t(_p(
                    'guildset:screen_blacklist|set_response:unset',
                    "Members will no longer be automatically blacklisted from screen share channels."
                ))
            return resp

        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            t = ctx_translator.get().t
            if data is not None:
                return super()._format_data(parent_id, data, **kwargs)
            else:
                return t(_p(
                    'guildset:screen_blacklist|formatted:unset',
                    "Not Set. (Members will not be automatically blacklisted.)"
                ))

    class ScreenBlacklistDurations(ListData, ListSetting, InteractiveSetting):
        setting_id = 'screen_durations'
        _setting = DurationSetting
        _write_ward = high_management_iward

        _display_name = _p('guildset:screen_durations', "screen_blacklist_durations")
        _desc = _p(
            'guildset:screen_durations|desc',
            "Sequence of durations for automatic screen share blacklists."
        )
        _long_desc = _p(
            'guildset:screen_durations|long_desc',
            "When `screen_blacklist` is set and members fail to share their screen within "
            "the configured `screen_grace_period`, they will be automatically blacklisted "
            "(i.e. given the `screen_blacklist` role).\n"
            "This setting describes *how long* the member will be blacklisted for, "
            "for each offence.\n"
            "E.g. if this is set to `1d, 7d, 30d`, "
            "then on the first offence the member will be blacklisted for 1 day, "
            "on the second for 7 days, and on the third for 30 days. "
            "A subsequent offence will result in an infinite blacklist."
        )
        _accepts = _p(
            'guildset:screen_durations|accepts',
            "Comma separated list of durations."
        )

        _default = [
            5 * 60,
            60 * 60,
            6 * 60 * 60,
            24 * 60 * 60,
            168 * 60 * 60,
            720 * 60 * 60
        ]

        _cache = {}

        _table_interface = ScreenData.screen_blacklist_durations
        _id_column = 'guildid'
        _data_column = 'duration'
        _order_column = 'rowid'

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'guildset:screen_durations|set_response:set',
                    "Members will be automatically blacklisted for: {durations}"
                )).format(durations=self.formatted)
            else:
                resp = t(_p(
                    'guildset:screen_durations|set_response:unset',
                    "Screen share blacklists are now always permanent."
                ))
            return resp

    class ScreenGracePeriod(ModelData, DurationSetting):
        setting_id = "screen_grace_period"
        _event = 'guildset_screen_grace_period'
        _write_ward = high_management_iward

        _display_name = _p('guildset:screen_grace_period', "screen_grace_period")
        _desc = _p(
            'guildset:screen_grace_period|desc',
            "How long to wait (in seconds) before kicking/blacklisting members who don't share their screen."
        )
        _long_desc = _p(
            'guildset:screen_grace_period|long_desc',
            "The length of time a member has to share their screen after joining a screen share channel. "
            "After this time, if they have not shared their screen, they will be kicked from the channel "
            "and potentially blacklisted from screen share channels."
        )
        _accepts = _p(
            'guildset:screen_grace_period|accepts',
            "How many seconds to wait for a member to share their screen."
        )
        _default = 90
        _default_multiplier = 1

        _model = CoreData.Guild
        _column = CoreData.Guild.screen_grace_period.name
        _cache = LRUCache(2500)

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            resp = t(_p(
                'guildset:screen_grace_period|set_response:set',
                "Members will now have **{duration}** to share their screen."
            )).format(duration=self.formatted)
            return resp

    class ScreenExempt(ListData, RoleListSetting):
        setting_id = "screen_exempt"
        _event = 'guildset_screen_exempt'
        _write_ward = high_management_iward

        _display_name = _p('guildset:screen_exempt', "screen_exempt")
        _desc = _p(
            'guildset:screen_exempt|desc',
            "List of roles which are exempt from screen share channels."
        )
        _long_desc = _p(
            'guildset:screen_exempt|long_desc',
            "Members who have **any** of these roles "
            "will not be required to share their screen in the `screen_channels`. "
            "This also overrides the `screen_blacklist` role."
        )
        _accepts = _p(
            'guildset:screen_exempt|accepts',
            "List of exempt role names or ids."
        )

        _table_interface = ScreenData.screen_exempt_roles
        _id_column = 'guildid'
        _data_column = 'roleid'
        _order_column = 'roleid'

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'guildset:screen_exempt|set_response:set',
                    "The following roles will now be exempt from screen share channels: {roles}"
                )).format(roles=self.formatted)
            else:
                resp = t(_p(
                    'guildset:screen_exempt|set_response:unset',
                    "No members will be exempt from screen share channel requirements."
                ))
            return resp

        @classmethod
        @log_wrap(action="Cache screen_exempt")
        async def setup(cls, bot):
            data: ScreenData = bot.db.registries[ScreenData._name]
            if bot.is_ready():
                rows = await data.screen_exempt_roles.select_where(
                    guildid=[guild.id for guild in bot.guilds]
                )
            else:
                rows = await data.screen_exempt_roles.select_where(THIS_SHARD)
            new_cache = defaultdict(list)
            count = 0
            for row in rows:
                new_cache[row['guildid']].append(row['roleid'])
                count += 1
            if cls._cache is None:
                cls._cache = LRUCache(2500)
            cls._cache.clear()
            cls._cache.update(new_cache)
            logger.info(f"Loaded {count} screen exempt roles on this shard.")
