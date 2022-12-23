import datetime

import settings
from utils.lib import DotDict

from data import tables as tb


class UserSettings(settings.ObjectSettings):
    settings = DotDict()


class UserSetting(settings.ColumnData, settings.Setting):
    _table_interface = tb.user_config
    _id_column = 'userid'
    _create_row = True

    write_ward = None


@UserSettings.attach_setting
class timezone(settings.Timezone, UserSetting):
    attr_name = 'timezone'
    _data_column = 'timezone'

    _default = 'UTC'

    display_name = 'timezone'
    desc = "Timezone to display prompts in."
    long_desc = (
        "Timezone used for displaying certain prompts (e.g. selecting an accountability room)."
    )

    @property
    def success_response(self):
        if self.value:
            return (
                "Your personal timezone is now {}.\n"
                "Your current time is **{}**."
            ).format(self.formatted, datetime.datetime.now(tz=self.value).strftime("%H:%M"))
        else:
            return "Your personal timezone has been unset."
