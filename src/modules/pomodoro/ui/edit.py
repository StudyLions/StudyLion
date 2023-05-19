from typing import Optional, TYPE_CHECKING

import discord
from discord.ui.text_input import TextInput, TextStyle

from meta import LionBot
from meta.errors import UserInputError

from utils.ui import FastModal, error_handler_for, ModalRetryUI
from utils.lib import parse_duration

from .. import babel, logger
from ..lib import TimerRole
from ..options import TimerOptions

if TYPE_CHECKING:
    from ..timer import Timer

_p = babel._p


class TimerEditor(FastModal):
    """
    Timer Option Editor

    Appearence depends on caller role
    (i.e. managers may edit focus/break times, owners may edit all fields.)
    """
    @classmethod
    async def open_editor(cls, bot: LionBot, interaction: discord.Interaction,
                          timer: 'Timer',
                          actor: discord.Member,
                          callback=None):
        role = timer.get_member_role(actor)
        if role >= TimerRole.OWNER:
            settings = [
                TimerOptions.FocusLength,
                TimerOptions.BreakLength,
                TimerOptions.InactivityThreshold,
                TimerOptions.BaseName,
                TimerOptions.ChannelFormat
            ]
        elif role is TimerRole.MANAGER:
            settings = [
                TimerOptions.FocusLength,
                TimerOptions.BreakLength,
            ]
        else:
            # This should be impossible
            raise ValueError("Timer Editor Opened by Invalid Role")
        instances = []
        inputs = []
        for setting in settings:
            instance = timer.config.get(setting.setting_id)
            input_field = instance.input_field
            instances.append(instance)
            inputs.append(input_field)

        self = cls(
            *inputs,
            title=bot.translator.t(_p(
                'modal:timer_editor|title',
                "Timer Option Editor"
            ))
        )

        @self.submit_callback(timeout=10*60)
        async def _edit_timer_callback(submit: discord.Interaction):
            # Parse each field
            # Parse errors will raise UserInputError and hence trigger ModalRetryUI
            try:
                data = timer.data
                update_args = {}
                modified = set()
                for instance, field in zip(instances, inputs):
                    try:
                        parsed = await instance.from_string(data.channelid, field.value)
                    except UserInputError as e:
                        _msg = f"`{instance.display_name}:` {e._msg}"
                        raise UserInputError(_msg, info=e.info, details=e.details)
                    update_args[parsed._column] = parsed._data
                    if data.data[parsed._column] != parsed._data:
                        modified.add(instance.setting_id)

                # Parsing successful, ack the submission
                await submit.response.defer(thinking=False)

                if modified:
                    await data.update(**update_args)
                    if ('focus_length' in modified or 'break_length' in modified) and timer.running:
                        # Regenerate timer
                        await timer.start()
                    else:
                        # Just update last status
                        # This will also update the warning list if the inactivity threshold is modified
                        await timer.update_status_card()
            except UserInputError:
                raise
            except Exception:
                logger.exception(
                    "Unhandled exception occurred during timer edit submission callback."
                )

            if callback is not None:
                await callback(submit)

        # Editor prepared, now send and return
        await interaction.response.send_modal(self)
        return self

    @error_handler_for(UserInputError)
    async def rerequest(self, interaction: discord.Interaction, error: UserInputError):
        await ModalRetryUI(self, error.msg).respond_to(interaction)
