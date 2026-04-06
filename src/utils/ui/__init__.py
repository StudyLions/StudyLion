import asyncio
import logging
from .. import util_babel

logger = logging.getLogger(__name__)

from .hooked import *
from .leo import *
from .micros import *
from .pagers import *
from .transformed import *
from .config import *
from .msgeditor import *

# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Monkey-patch InteractionResponse.send_modal to auto-truncate Modal title,
# TextInput labels, and TextInput placeholders to Discord's character limits,
# preventing 400 Bad Request errors from overly long translations.
# Limits: Modal title = 45, TextInput label = 45, TextInput placeholder = 100.
# --- Original code (commented out for rollback) ---
# (Previous version from 2026-03-24 only truncated title and label, not placeholder)
# --- End original code ---
import discord
from discord.ui import TextInput as _TextInput

_original_send_modal = discord.InteractionResponse.send_modal

async def _safe_send_modal(self, modal, /):
    MAX_TITLE = 45
    MAX_LABEL = 45
    MAX_PLACEHOLDER = 100
    if hasattr(modal, 'title') and isinstance(modal.title, str) and len(modal.title) > MAX_TITLE:
        modal.title = modal.title[:MAX_TITLE]
    for item in modal.children:
        if isinstance(item, _TextInput):
            if isinstance(item.label, str) and len(item.label) > MAX_LABEL:
                item.label = item.label[:MAX_LABEL]
            if isinstance(item.placeholder, str) and len(item.placeholder) > MAX_PLACEHOLDER:
                item.placeholder = item.placeholder[:MAX_PLACEHOLDER]
    return await _original_send_modal(self, modal)

discord.InteractionResponse.send_modal = _safe_send_modal
# --- END AI-MODIFIED ---


# def create_task_in(coro, context: Context):
#     """
#     Transitional.
#     Since py3.10 asyncio does not support context instantiation,
#     this helper method runs `asyncio.create_task(coro)` inside the given context.
#     """
#     return context.run(asyncio.create_task, coro)
