# ============================================================
# AI-GENERATED FILE
# Created: 2026-04-06
# Purpose: Discord UI components for Anti AFK System.
#          Uses on_interaction listener for persistent handling
#          of dynamic custom_ids (same pattern as LionGotchi
#          family invites). The confirm button encodes the guild
#          ID so DM-mode buttons work across restarts.
# ============================================================
import discord
from discord.ui import View, Button
from discord import ButtonStyle

from . import logger

CUSTOM_ID_PREFIX = 'anti_afk:confirm'


class AntiAfkConfirmView(View):
    """
    View with an "I'm still here" button, sent with each check prompt.

    The custom_id encodes the guild ID and target user ID so it works
    in both VC text and DM delivery modes, and so only the target user
    can confirm their own check. Handled via on_interaction listener in
    the cog (not via bot.add_view) because the dynamic IDs make each
    custom_id unique -- static persistent views can't match them.
    """

    # --- AI-MODIFIED (2026-04-24) ---
    # Purpose: Include userid in custom_id so only the pinged user can
    # confirm. Previously any user could click another's button and
    # silently confirm their own pending check by accident.
    def __init__(self, guildid: int, userid: int):
        super().__init__(timeout=None)

        self.confirm_button = Button(
            style=ButtonStyle.green,
            label="I'm still here!",
            emoji="\u2705",
            custom_id=f"{CUSTOM_ID_PREFIX}:{guildid}:{userid}",
        )
        self.add_item(self.confirm_button)
    # --- END AI-MODIFIED ---
