from settings.user_settings import UserSettings, UserSetting
from settings.setting_types import Boolean

from modules.reminders.reminder import Reminder
from modules.reminders.data import reminders

from .utils import *

@UserSettings.attach_setting
class topgg_vote_remainder(Boolean, UserSetting):
    attr_name = 'vote_remainder'
    _data_column = 'remaind_upvote'

    _default = True

    display_name = 'Upvote Remainder'
    desc = "Turn on/off DM Remainders to Upvote me."
    long_desc = "Use this setting to enable/disable DM remainders from me to upvote on Top.gg."

    @property
    def success_response(self):
        if self.value:
            # Check if reminder is already running
            create_remainder(self.id)

            return (
                "Remainder, in your DMs, to upvote me are {}.\n\n"
                "`Do make sure that I can DM you.`"
            ).format(self.formatted)
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
                "Remainder, in your DMs, to upvote me are Off."
            ).format(self.formatted)