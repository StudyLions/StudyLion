from settings import GuildSettings, GuildSetting
from wards import guild_admin

import settings

from .data import workout_channels


@GuildSettings.attach_setting
class workout_length(settings.Integer, GuildSetting):
    category = "Workout"

    attr_name = "min_workout_length"
    _data_column = "min_workout_length"

    display_name = "min_workout_length"
    desc = "Minimum length of a workout."

    _default = 20

    long_desc = (
        "Minimun time a user must spend in a workout channel for it to count as a valid workout. "
        "Value must be given in minutes."
    )
    _accepts = "An integer number of minutes."

    @property
    def success_response(self):
        return "The minimum workout length is now `{}` minutes.".format(self.formatted)


@GuildSettings.attach_setting
class workout_reward(settings.Integer, GuildSetting):
    category = "Workout"

    attr_name = "workout_reward"
    _data_column = "workout_reward"

    display_name = "workout_reward"
    desc = "Number of daily LionCoins to reward for completing a workout."

    _default = 350

    long_desc = (
        "Number of LionCoins given when a member completes their daily workout."
    )
    _accepts = "An integer number of LionCoins."

    @property
    def success_response(self):
        return "The workout reward is now `{}` LionCoins.".format(self.formatted)


@GuildSettings.attach_setting
class workout_channels_setting(settings.ChannelList, settings.ListData, settings.Setting):
    category = "Workout"

    attr_name = 'workout_channels'

    _table_interface = workout_channels
    _id_column = 'guildid'
    _data_column = 'channelid'
    _setting = settings.VoiceChannel

    write_ward = guild_admin
    display_name = "workout_channels"
    desc = "Channels in which members can do workouts."

    _force_unique = True

    long_desc = (
        "Sessions in these channels will be treated as workouts."
    )

    # Flat cache, no need to expire objects
    _cache = {}

    @property
    def success_response(self):
        if self.value:
            return "The workout channels have been updated:\n{}".format(self.formatted)
        else:
            return "The workout channels have been removed."
