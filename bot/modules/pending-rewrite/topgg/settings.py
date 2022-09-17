from cmdClient.checks import is_owner

from settings import UserSettings, UserSetting, AppSettings
from settings.base import ListData, Setting
from settings.setting_types import Boolean, GuildIDList

from modules.reminders.reminder import Reminder
from modules.reminders.data import reminders

from .utils import create_remainder, remainder_content, topgg_upvote_link
from .data import guild_whitelist


@UserSettings.attach_setting
class topgg_vote_remainder(Boolean, UserSetting):
    attr_name = 'vote_remainder'
    _data_column = 'topgg_vote_reminder'

    _default = True

    display_name = 'vote_reminder'
    desc = r"Toggle automatic reminders to support me for a 25% LionCoin boost."
    long_desc = (
        "Did you know that you can [vote for me]({vote_link}) to help me help other people reach their goals? "
        "And you get a **25% boost** to all LionCoin income you make across all servers!\n"
        "Enable this setting if you want me to let you know when you can vote again!"
    ).format(vote_link=topgg_upvote_link)

    @property
    def success_response(self):
        if self.value:
            # Check if reminder is already running
            create_remainder(self.id)

            return (
                "Thank you for supporting me! I will remind in your DMs when you can vote next! "
                "(Please make sure your DMs are open, otherwise I can't reach you!)"
            )
        else:
            # Check if reminder is already running and get its id
            r = reminders.select_one_where(
                userid=self.id,
                select_columns='reminderid',
                content=remainder_content,
                _extra="ORDER BY remind_at DESC LIMIT 1"
            )

            # Cancel and delete Remainder if already running
            if r:
                Reminder.delete(r['reminderid'])

            return (
                "I will no longer send you voting reminders."
            )


@AppSettings.attach_setting
class topgg_guild_whitelist(GuildIDList, ListData, Setting):
    attr_name = 'topgg_guild_whitelist'
    write_ward = is_owner

    category = 'Topgg Voting'
    display_name = 'topgg_hidden_in'
    desc = "Guilds where the topgg vote prompt is not displayed."
    long_desc = (
        "A list of guilds where the topgg vote prompt will be hidden."
    )

    _table_interface = guild_whitelist
    _id_column = 'appid'
    _data_column = 'guildid'
    _force_unique = True
