"""
Temporary patches for the discord.py library to support new features of the discord API.
"""
from discord.http import Route, HTTPClient
from discord.abc import Messageable
from discord.utils import InvalidArgument
from discord import File, AllowedMentions


def send_message(self, channel_id, content, *, tts=False, embeds=None,
                 nonce=None, allowed_mentions=None, message_reference=None):
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

    return self.request(r, json=payload)


HTTPClient.send_message = send_message


async def send(self, content=None, *, tts=False, embed=None, embeds=None, file=None,
               files=None, delete_after=None, nonce=None,
               allowed_mentions=None, reference=None,
               mention_author=None):

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
                                               message_reference=reference)
        finally:
            file.close()

    elif files is not None:
        if len(files) > 10:
            raise InvalidArgument('files parameter must be a list of up to 10 elements')
        elif not all(isinstance(file, File) for file in files):
            raise InvalidArgument('files parameter must be a list of File')

        try:
            data = await state.http.send_files(channel.id, files=files, content=content, tts=tts,
                                               embed=embed, nonce=nonce, allowed_mentions=allowed_mentions,
                                               message_reference=reference)
        finally:
            for f in files:
                f.close()
    else:
        data = await state.http.send_message(channel.id, content, tts=tts, embeds=embeds,
                                             nonce=nonce, allowed_mentions=allowed_mentions,
                                             message_reference=reference)

    ret = state.create_message(channel=channel, data=data)
    if delete_after is not None:
        await ret.delete(delay=delete_after)
    return ret

Messageable.send = send
