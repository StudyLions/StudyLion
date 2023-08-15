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

from . import babel, logger
from .data import VideoData

_p = babel._p


class VideoSettings(SettingGroup):
    class VideoChannels(ListData, ChannelListSetting):
        setting_id = "video_channels"
        _event = 'guildset_video_channels'
        
        _display_name = _p('guildset:video_channels', "video_channels")
        _desc = _p(
            'guildset:video_channels|desc',
            "List of voice channels and categories in which to enforce video."
        )
        _long_desc = _p(
            'guildset:video_channels|long_desc',
            "Member will be required to turn on their video in these channels.\n"
            "If they do not enable their video with `15` seconds of joining, "
            "they will be asked to enable it "
            "through a notification in direct messages or the `alert_channel`. "
            "If they still have not enabled it after the `video_grace_period` has passed, "
            "they will be kicked from the channel. "
            "Further, after the first offence (which is considered a warning), "
            "they will be given the `video_blacklist` role, if configured, "
            "which will stop them from joining video channels.\n"
            "As usual, if a category is configured, this will apply to all voice channels "
            "under the category."
        )
        _accepts = _p(
            'guildset:video_channels|accepts',
            "Comma separated channel ids or names."
        )

        _cache = LRUCache(maxsize=2500)
        
        _table_interface = VideoData.video_channels
        _id_column = 'guildid'
        _data_column = 'channelid'
        _order_column = 'channelid'
        
        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'guildset:video_channels|set_response:set',
                    "Members will be asked to turn on their video in the following channels: {channels}"
                )).format(channels=self.formatted)
            else:
                resp = t(_p(
                    'guildset:video_channels|set_response:unset',
                    "Members will not be asked to turn on their video in any channels."
                ))
            return resp

        @classmethod
        @log_wrap(action="Cache video_channels")
        async def setup(cls, bot):
            """
            Preload video channels for every guild on the current shard.
            """
            data: VideoData = bot.db.registries[VideoData._name]
            if bot.is_ready():
                rows = await data.video_channels.select_where(
                    guildid=[guild.id for guild in bot.guilds]
                )
            else:
                rows = await data.video_channels.select_where(THIS_SHARD)
            new_cache = defaultdict(list)
            count = 0
            for row in rows:
                new_cache[row['guildid']].append(row['channelid'])
                count += 1
            if cls._cache is None:
                cls._cache = LRUCache(2500)
            cls._cache.clear()
            cls._cache.update(new_cache)
            logger.info(f"Loaded {count} video channels on this shard.")


    class VideoBlacklist(ModelData, RoleSetting):
        setting_id = "video_blacklist"
        _event = 'guildset_video_blacklist'
        
        _display_name = _p('guildset:video_blacklist', "video_blacklist")
        _desc = _p(
            'guildset:video_blacklist|desc',
            "Role given when members are blacklisted from video channels."
        )
        _long_desc = _p(
            'guildset:video_blacklist|long_desc',
            "This role will be automatically given after a member has failed to keep their video "
            "enabled in a video channel (see above).\n"
            "Members who have this role will not be able to join configured video channels. "
            "The role permissions may be freely configured by server admins "
            "to place further restrictions on the offender.\n"
            "The role may also be manually assigned, to the same effect.\n"
            "If this role is not set, no video blacklist will occur, "
            "and members will only be kicked from the channel and warned."
        )
        _accepts = _p(
            'guildset:video_blacklist|accepts',
            "Blacklist role name or id."
        )
        _default = None
        
        _model = CoreData.Guild
        _column = CoreData.Guild.studyban_role.name
        _allow_object = False
        
        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'guildset:video_blacklist|set_response:set',
                    "Members who fail to keep their video on will be given {role}"
                )).format(role=f"<@&{self.data}>")
            else:
                resp = t(_p(
                    'guildset:video_blacklist|set_response:unset',
                    "Members will no longer be automatically blacklisted from video channels."
                ))
            return resp
        
        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            t = ctx_translator.get().t
            if data is not None:
                return super()._format_data(parent_id, data, **kwargs)
            else:
                return t(_p(
                    'guildset:video_blacklist|formatted:unset',
                    "Not Set. (Members will not be automatically blacklisted.)"
                ))

    class VideoBlacklistDurations(ListData, ListSetting, InteractiveSetting):
        setting_id = 'video_durations'
        _setting = DurationSetting

        _display_name = _p('guildset:video_durations', "video_blacklist_durations")
        _desc = _p(
            'guildset:video_durations|desc',
            "Sequence of durations for automatic video blacklists."
        )
        _long_desc = _p(
            'guildset:video_durations|long_desc',
            "When `video_blacklist` is set and members fail to turn on their video within "
            "the configured `video_grace_period`, they will be automatically blacklisted "
            "(i.e. given the `video_blacklist` role).\n"
            "This setting describes *how long* the member will be blacklisted for, "
            "for each offence.\n"
            "E.g. if this is set to `1d, 7d, 30d`, "
            "then on the first offence the member will be blacklisted for 1 day, "
            "on the second for 7 days, and on the third for 30 days. "
            "A subsequent offence will result in an infinite blacklist."
        )
        _accepts = _p(
            'guildset:video_durations|accepts',
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

        # No need to expire
        _cache = {}

        _table_interface = VideoData.video_blacklist_durations
        _id_column = 'guildid'
        _data_column = 'duration'
        _order_column = 'rowid'
        
        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'guildset:video_durations|set_response:set',
                    "Members will be automatically blacklisted for: {durations}"
                )).format(durations=self.formatted)
            else:
                resp = t(_p(
                    'guildset:video_durations|set_response:unset',
                    "Video blacklists are now always permanent."
                ))
            return resp

    class VideoGracePeriod(ModelData, DurationSetting):
        setting_id = "video_grace_period"
        _event = 'guildset_video_grace_period'
        
        _display_name = _p('guildset:video_grace_period', "video_grace_period")
        _desc = _p(
            'guildset:video_grace_period|desc',
            "How long to wait (in seconds) before kicking/blacklist members who don't enable their video."
        )
        _long_desc = _p(
            'guildset:video_grace_period|long_desc',
            "The length of time a member has to enable their video after joining a video channel. "
            "After this time, if they have not enabled their video, they will be kicked from the channel "
            "and potentially blacklisted from video channels."
        )
        _accepts = _p(
            'guildset:video_grace_period|accepts',
            "How many seconds to wait for a member to enable video."
        )
        _default = 90
        _default_multiplier = 1
        
        _model = CoreData.Guild
        _column = CoreData.Guild.video_grace_period.name
        _cache = LRUCache(2500)
        
        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            resp = t(_p(
                'guildset:video_grace_period|set_response:set',
                "Members will now have **{duration}** to enable their video."
            )).format(duration=self.formatted)
            return resp

    class VideoExempt(ListData, RoleListSetting):
        setting_id = "video_exempt"
        _event = 'guildset_video_exempt'
        
        _display_name = _p('guildset:video_exempt', "video_exempt")
        _desc = _p(
            'guildset:video_exempt|desc',
            "List of roles which are exempt from video channels."
        )
        _long_desc = _p(
            'guildset:video_exempt|long_desc',
            "Members who have **any** of these roles "
            "will not be required to enable their video in the `video_channels`. "
            "This also overrides the `video_blacklist` role."
        )
        _accepts = _p(
            'guildset:video_exempt|accepts',
            "List of exempt role names or ids."
        )
        
        _table_interface = VideoData.video_exempt_roles
        _id_column = 'guildid'
        _data_column = 'roleid'
        _order_column = 'roleid'
        
        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'guildset:video_exempt|set_response:set',
                    "The following roles will now be exempt from video channels: {roles}"
                )).format(roles=self.formatted)
            else:
                resp = t(_p(
                    'guildset:video_exempt|set_response:unset',
                    "No members will be exempt from video channel requirements."
                ))
            return resp

        @classmethod
        @log_wrap(action="Cache video_exempt")
        async def setup(cls, bot):
            """
            Preload video exempt roles for every guild on the current shard.
            """
            data: VideoData = bot.db.registries[VideoData._name]
            if bot.is_ready():
                rows = await data.video_exempt_roles.select_where(
                    guildid=[guild.id for guild in bot.guilds]
                )
            else:
                rows = await data.video_exempt_roles.select_where(THIS_SHARD)
            new_cache = defaultdict(list)
            count = 0
            for row in rows:
                new_cache[row['guildid']].append(row['roleid'])
                count += 1
            if cls._cache is None:
                cls._cache = LRUCache(2500)
            cls._cache.clear()
            cls._cache.update(new_cache)
            logger.info(f"Loaded {count} video exempt roles on this shard.")
