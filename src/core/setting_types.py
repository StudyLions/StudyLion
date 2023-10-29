"""
Additional abstract setting types useful for StudyLion settings.
"""
from typing import Optional
import json
import traceback

import discord
from discord.enums import TextStyle

from settings.base import ParentID
from settings.setting_types import IntegerSetting, StringSetting
from meta import conf
from meta.errors import UserInputError
from constants import MAX_COINS
from babel.translator import ctx_translator
from utils.lib import MessageArgs

from . import babel

_p = babel._p


class CoinSetting(IntegerSetting):
    """
    Setting type mixin describing a LionCoin setting.
    """
    _min = 0
    _max = MAX_COINS

    _accepts = _p('settype:coin|accepts', "A positive integral number of coins.")

    @classmethod
    async def _parse_string(cls, parent_id, string: str, **kwargs):
        """
        Parse the user input into an integer.
        """
        if not string:
            return None
        try:
            num = int(string)
        except Exception:
            t = ctx_translator.get().t

            raise UserInputError(t(_p(
                'settype:coin|parse|error:notinteger',
                "The coin quantity must be a positive integer!"
            ))) from None

        if num > cls._max:
            t = ctx_translator.get().t
            raise UserInputError(
                t(_p(
                    'settype:coin|parse|error:too_large',
                    "You cannot set this to more than {coin}**{max}**!"
                )).format(coin=conf.emojis.coin, max=cls._max)
            ) from None
        elif num < cls._min:
            t = ctx_translator.get().t
            raise UserInputError(
                t(_p(
                    'settype:coin|parse|error:too_small',
                    "You cannot set this to less than {coin}**{min}**!"
                )).format(coin=conf.emojis.coin, min=cls._min)
            ) from None

        return num

    @classmethod
    def _format_data(cls, parent_id, data, **kwargs):
        if data is not None:
            t = ctx_translator.get().t
            formatted = t(_p(
                'settype:coin|formatted',
                "{coin}**{amount}**"
            )).format(coin=conf.emojis.coin, amount=data)
            return formatted


class MessageSetting(StringSetting):
    """
    Typed Setting ABC representing a message sent to Discord.

    Data is a json-formatted string dict with at least one of the fields 'content', 'embed', 'embeds'
    Value is the corresponding dictionary
    """
    # TODO: Extend to support format keys

    _accepts = _p(
        'settype:message|accepts',
        "JSON formatted raw message data"
    )

    @staticmethod
    async def download_attachment(attached: discord.Attachment):
        """
        Download a discord.Attachment with some basic filetype and file size validation.
        """
        t = ctx_translator.get().t

        error = None
        decoded = None
        if attached.content_type and not ('json' in attached.content_type):
            error = t(_p(
                'settype:message|download|error:not_json',
                "The attached message data is not a JSON file!"
            ))
        elif attached.size > 10000:
            error = t(_p(
                'settype:message|download|error:size',
                "The attached message data is too large!"
            ))
        else:
            content = await attached.read()
            try:
                decoded = content.decode('UTF-8')
            except UnicodeDecodeError:
                error = t(_p(
                    'settype:message|download|error:decoding',
                    "Could not decode the message data. Please ensure it is saved with the `UTF-8` encoding."
                ))

        if error is not None:
            raise UserInputError(error)
        else:
            return decoded

    @classmethod
    def value_to_args(cls, parent_id: ParentID, value: dict, **kwargs) -> MessageArgs:
        if not value:
            return None

        args = {}
        args['content'] = value.get('content', "")
        if 'embed' in value:
            embed = discord.Embed.from_dict(value['embed'])
            args['embed'] = embed
        if 'embeds' in value:
            embeds = []
            for embed_data in value['embeds']:
                embeds.append(discord.Embed.from_dict(embed_data))
            args['embeds'] = embeds
        return MessageArgs(**args)

    @classmethod
    def _data_from_value(cls, parent_id: ParentID, value: Optional[dict], **kwargs):
        if value and any(value.get(key, None) for key in ('content', 'embed', 'embeds')):
            data = json.dumps(value)
        else:
            data = None
        return data

    @classmethod
    def _data_to_value(cls, parent_id: ParentID, data: Optional[str], **kwargs):
        if data:
            value = json.loads(data)
        else:
            value = None
        return value

    @classmethod
    async def _parse_string(cls, parent_id: ParentID, string: str, **kwargs):
        """
        Provided user string can be downright random.

        If it isn't json-formatted, treat it as the content of the message.
        If it is, do basic checking on the length and embeds.
        """
        string = string.strip()
        if not string or string.lower() == 'none':
            return None

        t = ctx_translator.get().t

        error_tip = t(_p(
            'settype:message|error_suffix',
            "You can view, test, and fix your embed using the online [embed builder]({link})."
        )).format(
            link="https://glitchii.github.io/embedbuilder/?editor=json"
        )

        if string.startswith('{') and string.endswith('}'):
            # Assume the string is a json-formatted message dict
            try:
                value = json.loads(string)
            except json.JSONDecodeError as err:
                error = t(_p(
                    'settype:message|error:invalid_json',
                    "The provided message data was not a valid JSON document!\n"
                    "`{error}`"
                )).format(error=str(err))
                raise UserInputError(error + '\n' + error_tip)

            if not isinstance(value, dict) or not any(value.get(key, None) for key in ('content', 'embed', 'embeds')):
                error = t(_p(
                    'settype:message|error:json_missing_keys',
                    "Message data must be a JSON object with at least one of the following fields: "
                    "`content`, `embed`, `embeds`"
                ))
                raise UserInputError(error + '\n' + error_tip)

            embed_data = value.get('embed', None)
            if not isinstance(embed_data, dict):
                error = t(_p(
                    'settype:message|error:json_embed_type',
                    "`embed` field must be a valid JSON object."
                ))
                raise UserInputError(error + '\n' + error_tip)

            embeds_data = value.get('embeds', [])
            if not isinstance(embeds_data, list):
                error = t(_p(
                    'settype:message|error:json_embeds_type',
                    "`embeds` field must be a list."
                ))
                raise UserInputError(error + '\n' + error_tip)

            if embed_data and embeds_data:
                error = t(_p(
                    'settype:message|error:json_embed_embeds',
                    "Message data cannot include both `embed` and `embeds`."
                ))
                raise UserInputError(error + '\n' + error_tip)

            content_data = value.get('content', "")
            if not isinstance(content_data, str):
                error = t(_p(
                    'settype:message|error:json_content_type',
                    "`content` field must be a string."
                ))
                raise UserInputError(error + '\n' + error_tip)

            # Validate embeds, which is the most likely place for something to go wrong
            embeds = [embed_data] if embed_data else embeds_data
            try:
                for embed in embeds:
                    discord.Embed.from_dict(embed)
            except Exception as e:
                # from_dict may raise a range of possible exceptions.
                raw_error = ''.join(
                    traceback.TracebackException.from_exception(e).format_exception_only()
                )
                error = t(_p(
                    'ui:settype:message|error:embed_conversion',
                    "Could not parse the message embed data.\n"
                    "**Error:** `{exception}`"
                )).format(exception=raw_error)
                raise UserInputError(error + '\n' + error_tip)

            # At this point, the message will at least successfully convert into MessageArgs
            # There are numerous ways it could still be invalid, e.g. invalid urls, or too-long fields
            # or the total message content being too long, or too many fields, etc
            # This will need to be caught in anything which displays a message parsed from user data.
        else:
            # Either the string is not json formatted, or the formatting is broken
            # Assume the string is a content message
            value = {
                'content': string
            }
        return json.dumps(value)

    @classmethod
    def _format_data(cls, parent_id: ParentID, data: Optional[str], **kwargs):
        if not data:
            return None

        value = cls._data_to_value(parent_id, data, **kwargs)
        content = value.get('content', "")
        if 'embed' in value or 'embeds' in value or len(content) > 100:
            t = ctx_translator.get().t
            formatted = t(_p(
                'settype:message|format:too_long',
                "Too long to display! See Preview."
            ))
        else:
            formatted = content

        return formatted

    @property
    def input_field(self):
        field = super().input_field
        field.style = TextStyle.long
        return field
