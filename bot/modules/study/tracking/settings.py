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
            cache = {guildid: [] for guildid in active_guildids}
            rows = cls._table_interface.select_where(
                guildid=active_guildids
            )
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
    _max = 32767

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
    _max = 32767

    long_desc = (
        "LionCoin bonus earnt for every hour a member streams in a voice channel, including video. "
        "This is in addition to the standard `hourly_reward`."
    )
    _accepts = "An integer number of LionCoins to reward."

    @property
    def success_response(self):
        return "Members will be rewarded an extra `{}` LionCoins per hour if they stream.".format(self.formatted)


@GuildSettings.attach_setting
class daily_study_cap(settings.Duration, settings.GuildSetting):
    category = "Study Tracking"

    attr_name = "daily_study_cap"
    _data_column = "daily_study_cap"

    display_name = "daily_study_cap"
    desc = "Maximum amount of recorded study time per member per day."

    _default = 16 * 60 * 60
    _default_multiplier = 60 * 60

    _max = 25 * 60 * 60

    long_desc = (
        "The maximum amount of study time that can be recorded for a member per day, "
        "intended to remove system encouragement for unhealthy or obsessive behaviour.\n"
        "The member may study for longer, but their sessions will not be tracked. "
        "The start and end of the day are determined by the member's configured timezone."
    )

    @property
    def success_response(self):
        # Refresh expiry for all sessions in the guild
        [session.schedule_expiry() for session in self.client.objects['sessions'][self.id].values()]

        return "The maximum tracked daily study time is now {}.".format(self.formatted)
