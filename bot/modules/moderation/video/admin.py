from collections import defaultdict

from settings import GuildSettings, GuildSetting
from wards import guild_admin

import settings

from .data import video_channels


@GuildSettings.attach_setting
class video_channels(settings.ChannelList, settings.ListData, settings.Setting):
    category = "Video Channels"

    attr_name = 'video_channels'

    _table_interface = video_channels
    _id_column = 'guildid'
    _data_column = 'channelid'
    _setting = settings.VoiceChannel

    write_ward = guild_admin
    display_name = "video_channels"
    desc = "Channels where members are required to enable their video."

    _force_unique = True

    long_desc = (
        "Members must keep their video enabled in these channels.\n"
        "If they do not keep their video enabled, they will be asked to enable it in their DMS after `15` seconds, "
        "and then kicked from the channel with another warning after the `video_grace_period` duration has passed.\n"
        "After the first offence, if the `video_studyban` is enabled and the `studyban_role` is set, "
        "they will also be automatically studybanned."
    )

    # Flat cache, no need to expire objects
    _cache = {}

    @property
    def success_response(self):
        if self.value:
            return "Members must enable their video in the following channels:\n{}".format(self.formatted)
        else:
            return "There are no video-required channels set up."

    @classmethod
    async def launch_task(cls, client):
        """
        Launch initialisation step for the `video_channels` setting.

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


@GuildSettings.attach_setting
class video_studyban(settings.Boolean, GuildSetting):
    category = "Video Channels"

    attr_name = 'video_studyban'
    _data_column = 'video_studyban'

    display_name = "video_studyban"
    desc = "Whether to studyban members if they don't enable their video."

    long_desc = (
        "If enabled, members who do not enable their video in the configured `video_channels` will be "
        "study-banned after a single warning.\n"
        "When disabled, members will only be warned and removed from the channel."
    )

    _default = True
    _outputs = {True: "Enabled", False: "Disabled"}

    @property
    def success_response(self):
        if self.value:
            return "Members will now be study-banned if they don't enable their video in the configured video channels."
        else:
            return "Members will not be study-banned if they don't enable their video in video channels."


@GuildSettings.attach_setting
class video_grace_period(settings.Duration, GuildSetting):
    category = "Video Channels"

    attr_name = 'video_grace_period'
    _data_column = 'video_grace_period'

    display_name = "video_grace_period"
    desc = "How long to wait before kicking/studybanning members who don't enable their video."

    long_desc = (
        "The period after a member has been asked to enable their video in a video-only channel "
        "before they will be kicked from the channel, and warned or studybanned (if enabled)."
    )

    _default = 45
    _default_multiplier = 1

    @classmethod
    def _format_data(cls, id: int, data, **kwargs):
        """
        Return the string version of the data.
        """
        if data is None:
            return None
        else:
            return "`{} seconds`".format(data)

    @property
    def success_response(self):
        return (
            "Members who do not enable their video will "
            "be disconnected after {}.".format(self.formatted)
        )
