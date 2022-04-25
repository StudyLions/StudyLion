"""
Temporary patches for the discord.py library to support new features of the discord API.
"""
import logging

from json import JSONEncoder

from discord.state import ConnectionState
from discord.http import Route, HTTPClient
from discord.abc import Messageable
from discord.utils import InvalidArgument, _get_as_snowflake, to_json
from discord import File, AllowedMentions, Member, User, Message

from .interactions import _component_interaction_factory, ModalResponse
from .interactions.enums import InteractionType


log = logging.getLogger(__name__)


def _default(self, obj):
    return getattr(obj.__class__, "to_json", _default.default)(obj)


_default.default = JSONEncoder().default
JSONEncoder.default = _default


def send_message(self, channel_id, content, *, tts=False, embeds=None,
                 nonce=None, allowed_mentions=None, message_reference=None, components=None):
    r = Route('POST', '/channels/{channel_id}/messages', channel_id=channel_id)
    payload = {}

    if content:
        payload['content'] = content

    if tts:
        payload['tts'] = True

    if embeds:
        payload['embeds'] = embeds

    if nonce:
        payload['nonce'] = nonce

    if allowed_mentions:
        payload['allowed_mentions'] = allowed_mentions

    if message_reference:
        payload['message_reference'] = message_reference

    if components:
        payload['components'] = components

    return self.request(r, json=payload)


def send_files(
    self,
    channel_id, *,
    files,
    content=None, tts=False, embed=None, embeds=None, nonce=None, allowed_mentions=None, message_reference=None,
    components=None
):
    r = Route('POST', '/channels/{channel_id}/messages', channel_id=channel_id)
    form = []

    payload = {'tts': tts}
    if content:
        payload['content'] = content
    if embed:
        payload['embed'] = embed
    if embeds:
        payload['embeds'] = embeds
    if nonce:
        payload['nonce'] = nonce
    if allowed_mentions:
        payload['allowed_mentions'] = allowed_mentions
    if message_reference:
        payload['message_reference'] = message_reference
    if components:
        payload['components'] = components

    form.append({'name': 'payload_json', 'value': to_json(payload)})
    if len(files) == 1:
        file = files[0]
        form.append({
            'name': 'file',
            'value': file.fp,
            'filename': file.filename,
            'content_type': 'application/octet-stream'
        })
    else:
        for index, file in enumerate(files):
            form.append({
                'name': 'file%s' % index,
                'value': file.fp,
                'filename': file.filename,
                'content_type': 'application/octet-stream'
            })

    return self.request(r, form=form, files=files)


def interaction_callback(self, interaction_id, interaction_token, callback_type, callback_data=None):
    r = Route(
        'POST',
        '/interactions/{interaction_id}/{interaction_token}/callback',
        interaction_id=interaction_id,
        interaction_token=interaction_token
    )

    payload = {}

    payload['type'] = int(callback_type)
    if callback_data:
        payload['data'] = callback_data

    return self.request(r, json=payload)


def edit_message(self, channel_id, message_id, components=None, **fields):
    r = Route('PATCH', '/channels/{channel_id}/messages/{message_id}', channel_id=channel_id, message_id=message_id)
    if components is not None:
        fields['components'] = [comp.to_dict() for comp in components]
    return self.request(r, json=fields)


HTTPClient.send_files = send_files
HTTPClient.send_message = send_message
HTTPClient.edit_message = edit_message
HTTPClient.interaction_callback = interaction_callback


async def send(self, content=None, *, tts=False, embed=None, embeds=None, file=None,
               files=None, delete_after=None, nonce=None,
               allowed_mentions=None, reference=None,
               mention_author=None, components=None):

    channel = await self._get_channel()
    state = self._state
    content = str(content) if content is not None else None
    if embed is not None:
        if embeds is not None:
            embeds.append(embed)
        else:
            embeds = [embed]
        embed = embed.to_dict()
    if embeds is not None:
        embeds = [embed.to_dict() for embed in embeds]

    if components is not None:
        components = [comp.to_dict() for comp in components]

    if allowed_mentions is not None:
        if state.allowed_mentions is not None:
            allowed_mentions = state.allowed_mentions.merge(allowed_mentions).to_dict()
        else:
            allowed_mentions = allowed_mentions.to_dict()
    else:
        allowed_mentions = state.allowed_mentions and state.allowed_mentions.to_dict()

    if mention_author is not None:
        allowed_mentions = allowed_mentions or AllowedMentions().to_dict()
        allowed_mentions['replied_user'] = bool(mention_author)

    if reference is not None:
        try:
            reference = reference.to_message_reference_dict()
        except AttributeError:
            raise InvalidArgument('reference parameter must be Message or MessageReference') from None

    if file is not None and files is not None:
        raise InvalidArgument('cannot pass both file and files parameter to send()')

    if file is not None:
        if not isinstance(file, File):
            raise InvalidArgument('file parameter must be File')

        try:
            data = await state.http.send_files(channel.id, files=[file], allowed_mentions=allowed_mentions,
                                               content=content, tts=tts, embed=embed, nonce=nonce,
                                               message_reference=reference, components=components)
        finally:
            file.close()

    elif files is not None:
        if len(files) > 10:
            raise InvalidArgument('files parameter must be a list of up to 10 elements')
        elif not all(isinstance(file, File) for file in files):
            raise InvalidArgument('files parameter must be a list of File')

        try:
            data = await state.http.send_files(channel.id, files=files, content=content, tts=tts,
                                               embeds=embeds, nonce=nonce, allowed_mentions=allowed_mentions,
                                               message_reference=reference, components=components)
        finally:
            for f in files:
                f.close()
    else:
        data = await state.http.send_message(channel.id, content, tts=tts, embeds=embeds,
                                             nonce=nonce, allowed_mentions=allowed_mentions,
                                             message_reference=reference, components=components)

    ret = state.create_message(channel=channel, data=data)
    if delete_after is not None:
        await ret.delete(delay=delete_after)
    return ret

Messageable.send = send


def parse_interaction_create(self, data):
    self.dispatch('raw_interaction_create', data)

    if (guild_id := data.get('guild_id', None)):
        guild = self._get_guild(int(guild_id))
        if guild is None:
            log.debug('INTERACTION_CREATE referencing an unknown guild ID: %s. Discarding.', guild_id)
            return
    else:
        guild = None

    if (member_data := data.get('member', None)) is not None:
        # Construct member
        # TODO: Theoretical reliance on cached guild
        user = Member(data=member_data, guild=guild, state=self)
    else:
        # Assume user
        user = self.get_user(_get_as_snowflake(data['user'], 'id')) or User(data=data['user'], state=self)

    if 'message' in data:
        message = self._get_message(_get_as_snowflake(data['message'], 'id'))
        if not message:
            message_data = data['message']
            channel, _ = self._get_guild_channel(message_data)
            message = Message(data=message_data, channel=channel, state=self)
            if self._messages is not None:
                self._messages.append(message)
    else:
        message = None

    interaction = None
    if data['type'] == InteractionType.MESSAGE_COMPONENT:
        interaction_class = _component_interaction_factory(data)
        if interaction_class:
            interaction = interaction_class(message, user, data, self)
        else:
            log.debug(
                'INTERACTION_CREATE recieved unhandled message component interaction type: %s',
                data['data']['component_type']
            )
    elif data['type'] == InteractionType.MODAL_SUBMIT:
        interaction = ModalResponse(message, user, data, self)
    else:
        log.debug('INTERACTION_CREATE recieved unhandled interaction type: %s', data['type'])
        log.debug(data)
        interaction = None

    if interaction:
        self.dispatch('interaction_create', interaction)


ConnectionState.parse_interaction_create = parse_interaction_create
