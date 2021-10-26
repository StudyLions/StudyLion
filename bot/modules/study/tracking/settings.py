from collections import defaultdict

import settings
from settings import GuildSettings
from wards import guild_admin

from .data import untracked_channels


@GuildSettings.attach_setting
class untracked_channels(settings.ChannelList, settings.ListData, settings.Setting):
    category = "Study Tracking"

    attr_name = 'untracked_channels'

    _table_interface = untracked_channels
    _setting = settings.VoiceChannel

    _id_column = 'guildid'
    _data_column = 'channelid'

    write_ward = guild_admin
    display_name = "untracked_channels"
    desc = "Channels to ignore for study time tracking."

    _force_unique = True

    long_desc = (
        "Time spent in these voice channels won't add study time or lioncoins to the member."
    )

    # Flat cache, no need to expire objects
    _cache = {}

    @property
    def success_response(self):
        if self.value:
            return "The untracked channels have been updated:\n{}".format(self.formatted)
        else:
            return "Study time will now be counted in all channels."

    @classmethod
    async def launch_task(cls, client):
        """
        Launch initialisation step for the `untracked_channels` setting.

        Pre-fill cache for the guilds with currently active voice channels.
        """
        active_guildids = [
            guild.id
            for guild in client.guilds
            if any(channel.members for channel in guild.voice_channels)
        ]
        if active_guildids:
            rows = cls._table_interface.select_where(
                guildid=active_guildids
            )
            cache = defaultdict(list)
            for row in rows:
                cache[row['guildid']].append(row['channelid'])
            cls._cache.update(cache)
            client.log(
                "Cached {} untracked channels for {} active guilds.".format(
                    len(rows),
                    len(cache)
                ),
                context="UNTRACKED_CHANNELS"
            )


@GuildSettings.attach_setting
class hourly_reward(settings.Integer, settings.GuildSetting):
    category = "Study Tracking"

    attr_name = "hourly_reward"
    _data_column = "study_hourly_reward"

    display_name = "hourly_reward"
    desc = "Number of LionCoins given per hour of study."

    _default = 50

    long_desc = (
        "Each spent in a voice channel will reward this number of LionCoins."
    )
    _accepts = "An integer number of LionCoins to reward."

    @property
    def success_response(self):
        return "Members will be rewarded `{}` LionCoins per hour of study.".format(self.formatted)


@GuildSettings.attach_setting
class hourly_live_bonus(settings.Integer, settings.GuildSetting):
    category = "Study Tracking"

    attr_name = "hourly_live_bonus"
    _data_column = "study_hourly_live_bonus"

    display_name = "hourly_live_bonus"
    desc = "Number of extra LionCoins given for a full hour of streaming (via go live or video)."

    _default = 10

    long_desc = (
        "LionCoin bonus earnt for every hour a member streams in a voice channel, including video. "
        "This is in addition to the standard `hourly_reward`."
    )
    _accepts = "An integer number of LionCoins to reward."

    @property
    def success_response(self):
        return "Members will be rewarded an extra `{}` LionCoins per hour if they stream.".format(self.formatted)
