import asyncio

from settings import GuildSettings, GuildSetting
import settings

from . import Timer


@GuildSettings.attach_setting
class pomodoro_channel(settings.TextChannel, GuildSetting):
    category = "Study Tracking"

    attr_name = "pomodoro_channel"
    _data_column = "pomodoro_channel"

    display_name = "pomodoro_channel"
    desc = "Channel to send pomodoro timer status updates and alerts."

    _default = None

    long_desc = (
        "Channel to send pomodoro status updates to.\n"
        "Members studying in rooms with an attached timer will need to be able to see "
        "this channel to get notifications and react to the status messages."
    )
    _accepts = "Any text channel I can write to, or `None` to unset."

    @property
    def success_response(self):
        timers = Timer.fetch_guild_timers(self.id)
        if self.value:
            for timer in timers:
                if timer.reaction_message and timer.reaction_message.channel != self.value:
                    timer.reaction_message = None
                    asyncio.create_task(timer.update_last_status())
            return f"The pomodoro alerts and updates will now be sent to {self.value.mention}"
        else:
            deleted = 0
            for timer in timers:
                if not timer.text_channel:
                    deleted += 1
                    asyncio.create_task(timer.destroy())

            msg = "The pomodoro alert channel has been unset."
            if deleted:
                msg += f" `{deleted}` timers were subsequently deactivated."
            return msg
