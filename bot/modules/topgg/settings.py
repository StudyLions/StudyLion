from settings.user_settings import UserSettings, UserSetting
from settings.setting_types import Boolean

from modules.reminders.reminder import Reminder
from modules.reminders.data import reminders

from .utils import create_remainder, remainder_content, topgg_upvote_link


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
