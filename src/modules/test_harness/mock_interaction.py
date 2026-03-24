# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-20
# Purpose: Build mock discord.Interaction objects that capture
#          responses instead of sending HTTP requests to Discord.
#          Used by the test harness to exercise slash commands
#          without a real Discord user.
# ============================================================
import asyncio
import logging
import time
from typing import Any, Optional

import discord

logger = logging.getLogger(__name__)


class CapturedResponse:
    """Stores a single captured interaction response."""
    __slots__ = ('type', 'content', 'embeds', 'ephemeral', 'view', 'modal', 'kwargs', 'timestamp')

    def __init__(self, response_type: str, **kwargs):
        self.type = response_type
        self.content = kwargs.pop('content', None)
        self.embeds = kwargs.pop('embeds', [])
        self.ephemeral = kwargs.pop('ephemeral', False)
        self.view = kwargs.pop('view', None)
        self.modal = kwargs.pop('modal', None)
        self.kwargs = kwargs
        self.timestamp = time.monotonic()

    def to_dict(self) -> dict:
        result: dict[str, Any] = {'type': self.type}
        if self.content is not None:
            result['content'] = str(self.content)
        if self.embeds:
            result['embeds'] = []
            for emb in self.embeds:
                if isinstance(emb, discord.Embed):
                    result['embeds'].append(emb.to_dict())
                else:
                    result['embeds'].append(str(emb))
        if self.ephemeral:
            result['ephemeral'] = True
        if self.modal is not None:
            result['modal'] = type(self.modal).__name__
        return result


class MockInteractionResponse:
    """Replacement for discord.InteractionResponse that captures output."""

    def __init__(self, collector: list[CapturedResponse]):
        self._collector = collector
        self._responded = False

    def is_done(self) -> bool:
        return self._responded

    async def defer(self, *, thinking: bool = False, ephemeral: bool = False):
        self._responded = True
        self._collector.append(CapturedResponse(
            'defer', thinking=thinking, ephemeral=ephemeral
        ))

    async def send_message(
        self, content=None, *, embed=None, embeds=None,
        view=None, ephemeral=False, **kwargs
    ):
        self._responded = True
        all_embeds = list(embeds or [])
        if embed is not None:
            all_embeds.insert(0, embed)
        self._collector.append(CapturedResponse(
            'send_message', content=content, embeds=all_embeds,
            ephemeral=ephemeral, view=view, **kwargs
        ))

    async def send_modal(self, modal):
        self._responded = True
        self._collector.append(CapturedResponse('send_modal', modal=modal))


class MockFollowup:
    """Replacement for discord.Webhook (interaction followup) that captures output."""

    def __init__(self, collector: list[CapturedResponse]):
        self._collector = collector

    async def send(self, content=None, *, embed=None, embeds=None,
                   ephemeral=False, view=None, **kwargs):
        all_embeds = list(embeds or [])
        if embed is not None:
            all_embeds.insert(0, embed)
        self._collector.append(CapturedResponse(
            'followup_send', content=content, embeds=all_embeds,
            ephemeral=ephemeral, view=view, **kwargs
        ))
        return None


class MockInteraction(discord.Interaction):
    """Subclass that overrides HTTP-bound methods to capture responses locally."""
    __slots__ = ('_captured',)

    def __init__(self, *, data, state, captured):
        self._captured = captured
        super().__init__(data=data, state=state)
        self._cs_response = MockInteractionResponse(captured)
        self._cs_followup = MockFollowup(captured)

    async def edit_original_response(self, **kwargs):
        embeds = list(kwargs.get('embeds', []))
        if 'embed' in kwargs:
            embeds.insert(0, kwargs['embed'])
        self._captured.append(CapturedResponse(
            'edit_original', content=kwargs.get('content'),
            embeds=embeds, view=kwargs.get('view'),
        ))

    async def delete_original_response(self, **kwargs):
        self._captured.append(CapturedResponse('delete_original'))

    async def original_response(self):
        return None

    def is_expired(self) -> bool:
        return False


async def build_mock_interaction(
    bot,
    command_name: str,
    options: Optional[list[dict]] = None,
    guild_id: Optional[int] = None,
    channel_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> tuple[discord.Interaction, list[CapturedResponse]]:
    """
    Build a mock discord.Interaction for a slash command.

    Uses real guild/channel/user objects from the bot's cache when available,
    falling back to the first available guild otherwise.

    Returns (interaction, captured_responses) where captured_responses is a
    list that will be populated as the command handler sends responses.
    """
    captured: list[CapturedResponse] = []

    guild = None
    if guild_id:
        guild = bot.get_guild(guild_id)
    if guild is None:
        guild = next(iter(bot.guilds), None)

    if guild is None:
        raise RuntimeError("Bot is not in any guilds; cannot build mock interaction.")

    channel = None
    if channel_id and guild:
        channel = guild.get_channel(channel_id)
    if channel is None and guild:
        for ch in guild.text_channels:
            channel = ch
            break

    member = None
    if user_id and guild:
        member = guild.get_member(user_id)
    if member is None and guild:
        member = guild.me

    app_cmd = bot.tree.get_command(command_name)
    if app_cmd is None:
        parts = command_name.split()
        if len(parts) > 1:
            parent = bot.tree.get_command(parts[0])
            if parent is not None:
                for sub in parts[1:]:
                    found = None
                    for child in getattr(parent, 'commands', []):
                        if child.name == sub:
                            found = child
                            break
                    if found is None:
                        break
                    parent = found
                app_cmd = parent

    cmd_id = str(app_cmd.id) if app_cmd and hasattr(app_cmd, 'id') and app_cmd.id else "0"

    interaction_data: dict[str, Any] = {
        'id': str(int(time.time() * 1000) << 22),
        'application_id': str(bot.application_id or 0),
        'type': 2,  # APPLICATION_COMMAND
        'token': f'test-token-{int(time.time())}',
        'version': 1,
        'attachment_size_limit': 26214400,
        'entitlements': [],
        'authorizing_integration_owners': {},
        'locale': 'en-US',
        'data': {
            'id': cmd_id,
            'name': command_name.split()[0],
            'type': 1,  # CHAT_INPUT
            'options': options or [],
        },
    }

    if guild:
        interaction_data['guild_id'] = str(guild.id)
        interaction_data['guild'] = {'id': str(guild.id), 'locale': 'en-US'}
    if channel:
        interaction_data['channel_id'] = str(channel.id)
        interaction_data['channel'] = {
            'id': str(channel.id),
            'type': getattr(channel, 'type', discord.ChannelType.text).value
            if hasattr(getattr(channel, 'type', None), 'value') else 0,
            'permissions': '0',
        }
    if member:
        interaction_data['member'] = {
            'user': {
                'id': str(member.id),
                'username': member.name,
                'discriminator': str(getattr(member, 'discriminator', '0')),
                'avatar': None,
                'global_name': getattr(member, 'global_name', member.name),
            },
            'roles': [str(r.id) for r in getattr(member, 'roles', [])],
            'joined_at': '2024-01-01T00:00:00.000000+00:00',
            'deaf': False,
            'mute': False,
            'flags': 0,
            'permissions': str(member.guild_permissions.value) if hasattr(member, 'guild_permissions') else '0',
        }

    if len(command_name.split()) > 1:
        parts = command_name.split()
        inner_options = options or []
        for sub_name in reversed(parts[1:]):
            inner_options = [{
                'name': sub_name,
                'type': 1,  # SUB_COMMAND
                'options': inner_options,
            }]
        interaction_data['data']['options'] = inner_options

    interaction = MockInteraction(data=interaction_data, state=bot._connection, captured=captured)
    return interaction, captured
