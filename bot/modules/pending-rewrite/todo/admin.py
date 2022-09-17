from settings import GuildSettings, GuildSetting
import settings

from wards import guild_admin

from .data import tasklist_channels


@GuildSettings.attach_setting
class task_limit(settings.Integer, GuildSetting):
    category = "TODO List"

    attr_name = "task_limit"
    _data_column = "max_tasks"

    display_name = "task_limit"
    desc = "Maximum number of tasks each user may have."

    _default = 99

    long_desc = (
        "Maximum number of tasks each user may have in the todo system."
    )
    _accepts = "An integer number of tasks."

    @property
    def success_response(self):
        return "The task limit is now `{}`.".format(self.formatted)


@GuildSettings.attach_setting
class task_reward(settings.Integer, GuildSetting):
    category = "TODO List"

    attr_name = "task_reward"
    _data_column = "task_reward"

    display_name = "task_reward"
    desc = "Number of LionCoins given for each completed TODO task."

    _default = 50

    long_desc = (
        "LionCoin reward given for completing each task on the TODO list."
    )
    _accepts = "An integer number of coins."

    @property
    def success_response(self):
        return "Task completion will now reward `{}` LionCoins.".format(self.formatted)


@GuildSettings.attach_setting
class task_reward_limit(settings.Integer, GuildSetting):
    category = "TODO List"

    attr_name = "task_reward_limit"
    _data_column = "task_reward_limit"

    display_name = "task_reward_limit"
    desc = "Maximum number of task rewards given in each 24h period."

    _default = 10

    long_desc = (
        "Maximum number of times in each 24h period that TODO task completion can reward LionCoins."
    )
    _accepts = "An integer number of times."

    @property
    def success_response(self):
        return "LionCoins will only be reward `{}` timers per 24h".format(self.formatted)


@GuildSettings.attach_setting
class tasklist_channels_setting(settings.ChannelList, settings.ListData, settings.Setting):
    category = "TODO List"

    attr_name = 'tasklist_channels'

    _table_interface = tasklist_channels
    _id_column = 'guildid'
    _data_column = 'channelid'
    _setting = settings.TextChannel

    write_ward = guild_admin
    display_name = "todo_channels"
    desc = "Channels where members may use the todo list."

    _force_unique = True

    long_desc = (
        "Members will only be allowed to use the `todo` command in these channels."
    )

    # Flat cache, no need to expire objects
    _cache = {}

    @property
    def success_response(self):
        if self.value:
            return "The todo channels have been updated:\n{}".format(self.formatted)
        else:
            return "The `todo` command may now be used anywhere."

    @property
    def formatted(self):
        if not self.data:
            return "All channels!"
        else:
            return super().formatted
