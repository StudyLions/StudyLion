# ============================================================
# AI-GENERATED FILE
# Created: 2026-09-10
# Purpose: Append one fundraiser notice to interaction responses without
#          extra messages, API requests, database work or premium exemptions.
# ============================================================
from collections import OrderedDict
from functools import wraps
from hashlib import sha256
import logging
from time import monotonic

import discord
from discord.utils import MISSING

logger = logging.getLogger(__name__)

FUNDRAISER_URL = 'https://www.gofundme.com/f/keep-lionbot-online-a-new-home-for-leo'
NOTICE = ('**Without enough support, Leo may go offline at the end of 2026.**\n'
          f'[Learn how to help]({FUNDRAISER_URL})')
CONTENT_NOTICE = ('**Without enough support, Leo may go offline at the end of 2026.**\n'
                  f'[Learn how to help](<{FUNDRAISER_URL}>)')
PRESENTATION_KEYS = ('content', 'embed', 'embeds', 'file', 'files', 'attachments')


def _units(text):
    """Conservatively count Discord limits, including astral characters."""
    return len(str(text or '').encode('utf-16-le')) // 2


def _embed_units(embed):
    data = embed.to_dict()
    texts = [data.get('title'), data.get('description'),
             data.get('footer', {}).get('text'), data.get('author', {}).get('name')]
    for field in data.get('fields', []):
        texts.extend((field.get('name'), field.get('value')))
    return sum(_units(text) for text in texts)


def _is_notice(embed):
    return isinstance(embed, discord.Embed) and embed.description == NOTICE


def _mode(message):
    if message is None:
        return 'unknown'
    flags = getattr(message, 'flags', None)
    if flags is not None and getattr(flags, 'components_v2', False):
        return 'v2'
    if any(_is_notice(embed) for embed in getattr(message, 'embeds', ())):
        return 'embed'
    if CONTENT_NOTICE in (getattr(message, 'content', '') or ''):
        return 'content'
    return 'clear'


def add_notice(kwargs, *, editing=False, previous='unknown', allow_embed=True):
    """Return a copied payload and notice mode; never truncate feature output.

    'empty' means a known fresh deferred response. Omitted edit fields always
    preserve the original message. Unknown attachment-only edits stay untouched.
    """
    result = dict(kwargs)
    view = result.get('view', MISSING)
    if previous == 'v2' or (view is not MISSING and view is not None and view.has_components_v2()):
        return result, 'v2'
    if editing and not any(result.get(key, MISSING) is not MISSING for key in PRESENTATION_KEYS):
        return result, previous

    embed = result.get('embed', MISSING)
    embeds = result.get('embeds', MISSING)
    if embed is not MISSING and embeds is not MISSING:
        # Keep discord.py's own validation and error behavior.
        return result, previous
    explicit_embeds = embed is not MISSING or embeds is not MISSING
    content = result.get('content', MISSING)
    if editing and previous == 'unknown' and not (explicit_embeds and content is not MISSING):
        # A cache eviction must not duplicate an old notice in an omitted field.
        return result, previous

    if content is not MISSING and CONTENT_NOTICE in str(content or ''):
        previous = 'content'

    # A content-only edit must not replace omitted embeds or duplicate a notice
    # already in them. Likewise, keep an existing content notice in that format.
    if editing and previous == 'embed' and not explicit_embeds:
        return result, previous
    if previous == 'content':
        if content is MISSING:
            return result, previous
        return _add_content_notice(result, content, previous)

    if explicit_embeds or not editing or previous == 'empty':
        original_embeds = list(embeds or []) if embeds is not MISSING else ([embed] if embed else [])
        clean_embeds = [item for item in original_embeds if not _is_notice(item)]
        suppress = result.get('suppress_embeds', result.get('suppress', False))
        if allow_embed and not suppress and len(clean_embeds) < 10 and sum(_embed_units(item) for item in clean_embeds) + _units(NOTICE) <= 6000:
            result.pop('embed', None)
            result['embeds'] = [*clean_embeds, discord.Embed(description=NOTICE, colour=0xE9B949)]
            return result, 'embed'
        # A saturated embed payload may use remaining message content space.
        # Never replace omitted content on an edit; it may contain feature text.
        if content is not MISSING or not editing or previous == 'empty':
            return _add_content_notice(result, content, 'clear')
        return result, 'clear'

    if content is not MISSING:
        return _add_content_notice(result, content, previous)
    return result, previous


def _add_content_notice(result, content, previous):
    text = '' if content is MISSING or content is None else str(content)
    if CONTENT_NOTICE in text:
        return result, 'content'
    appended = f'{text}\n\n{CONTENT_NOTICE}' if text else CONTENT_NOTICE
    if _units(appended) <= 2000:
        result['content'] = appended
        return result, 'content'
    return result, 'clear' if previous == 'content' else previous


class FundraiserResponses:
    """Scoped public-method hooks, installed/uninstalled with the extension.

    The short-lived bounded cache stores only notice modes, never message
    bodies or interaction tokens. It connects defer -> followup -> original edit
    without fetching Discord messages. Uncached old edits preserve unknown fields.
    """
    def __init__(self, bot):
        self.bot = bot
        self._patches = []
        self._modes = OrderedDict()
        self._active = False

    def _get(self, key, default='unknown'):
        value = self._modes.get(key)
        if value is None:
            return default
        mode, at = value
        if monotonic() - at >= 900:
            self._modes.pop(key, None)
            return default
        self._modes.move_to_end(key)
        return mode

    def _put(self, key, mode):
        self._modes[key] = (mode, monotonic())
        self._modes.move_to_end(key)
        while len(self._modes) > 4096:
            self._modes.popitem(last=False)

    @staticmethod
    def _original_key(owner):
        return ('original', sha256(owner.token.encode()).digest())

    def _ours(self, owner, kind):
        if kind in ('response', 'defer', 'response_edit'):
            return owner._parent.client is self.bot
        if kind == 'original_edit':
            return owner.client is self.bot
        if kind in ('followup', 'followup_edit') and owner.type is not discord.WebhookType.application:
            return False
        get_client = getattr(owner._state, '_get_client', None)
        return get_client is not None and get_client() is self.bot

    def _prepare(self, owner, kind, args, kwargs):
        interaction = owner._parent if kind in ('response', 'response_edit', 'defer') else owner
        if kind == 'response':
            return self._original_key(interaction), 'empty', False
        if kind == 'original_edit':
            previous = self._get(self._original_key(interaction))
            if previous == 'unknown':
                previous = _mode(getattr(interaction, '_original_response', None))
            return self._original_key(interaction), previous, True
        if kind == 'response_edit':
            return self._original_key(interaction), _mode(interaction.message), True
        if kind == 'followup':
            return self._original_key(owner), 'empty', False
        if kind == 'followup_edit':
            message_id = args[0] if args else kwargs['message_id']
            return ('message', message_id), self._get(('message', message_id)), True
        # Message.edit is only extended for messages that already carry our notice.
        return ('message', owner.id), self._get(('message', owner.id), _mode(owner)), True

    def for_ui(self, kwargs, channel):
        """Decorate the existing user-requested MessageUI.send path only."""
        if not self._active:
            return kwargs
        guild = getattr(channel, 'guild', None)
        allow_embed = guild is None or channel.permissions_for(guild.me).embed_links
        payload, _ = add_notice(kwargs, allow_embed=allow_embed)
        return payload

    def _wrap(self, original, kind):
        @wraps(original)
        async def wrapped(owner, *args, **kwargs):
            if not self._active or not self._ours(owner, kind):
                return await original(owner, *args, **kwargs)
            if kind == 'defer':
                result = await original(owner, *args, **kwargs)
                parent = owner._parent
                previous = ('empty' if owner.type is discord.InteractionResponseType.deferred_channel_message
                            else _mode(parent.message))
                self._put(self._original_key(parent), previous)
                self._put(('permission', self._original_key(parent)),
                          not parent.guild_id or parent.app_permissions.embed_links)
                return result

            # Preserve positional content and all keyword flags/attachments/views.
            forwarded_args = args
            payload = dict(kwargs)
            if kind in ('response', 'followup') and args:
                if 'content' in kwargs:
                    return await original(owner, *args, **kwargs)
                payload['content'] = args[0]
                forwarded_args = args[1:]
            try:
                key, previous, editing = self._prepare(owner, kind, args, payload)
                if kind == 'message_edit' and previous not in ('embed', 'content'):
                    return await original(owner, *args, **kwargs)
                if kind in ('response', 'response_edit', 'original_edit'):
                    parent = owner._parent if kind != 'original_edit' else owner
                    allow_embed = not parent.guild_id or parent.app_permissions.embed_links
                    self._put(('permission', self._original_key(parent)), allow_embed)
                elif kind in ('followup', 'followup_edit'):
                    allow_embed = self._get(('permission', self._original_key(owner)), False)
                else:
                    guild = getattr(owner.channel, 'guild', None)
                    allow_embed = guild is None or owner.channel.permissions_for(guild.me).embed_links
                payload, mode = add_notice(payload, editing=editing, previous=previous, allow_embed=allow_embed)
            except Exception:
                logger.warning('Could not add fundraiser notice; sending the original response.', exc_info=True)
                return await original(owner, *args, **kwargs)

            result = await original(owner, *forwarded_args, **payload)
            if kind != 'followup' or self._get(key) == 'empty':
                self._put(key, mode)
            message_id = getattr(result, 'message_id', None) or getattr(result, 'id', None)
            if message_id is not None:
                self._put(('message', message_id), mode)
            return result
        return wrapped

    def install(self):
        if self._active:
            return
        self._active = True
        targets = (
            (discord.InteractionResponse, 'defer', 'defer'),
            (discord.InteractionResponse, 'send_message', 'response'),
            (discord.InteractionResponse, 'edit_message', 'response_edit'),
            (discord.Interaction, 'edit_original_response', 'original_edit'),
            (discord.Webhook, 'send', 'followup'),
            (discord.Webhook, 'edit_message', 'followup_edit'),
            (discord.Message, 'edit', 'message_edit'),
        )
        for cls, name, kind in targets:
            original = getattr(cls, name)
            replacement = self._wrap(original, kind)
            self._patches.append((cls, name, original, replacement))
            setattr(cls, name, replacement)

    def uninstall(self):
        self._active = False
        for cls, name, original, replacement in reversed(self._patches):
            if getattr(cls, name) is replacement:
                setattr(cls, name, original)
        self._patches.clear()
        self._modes.clear()
