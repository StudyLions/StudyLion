import logging
import traceback
import asyncio
import uuid
import json

from .enums import ButtonStyle, InteractionType


class MessageComponent:
    _type = None
    interaction_type = InteractionType.MESSAGE_COMPONENT

    def __init_(self, *args, **kwargs):
        self.message = None

    def to_dict(self):
        raise NotImplementedError

    def to_json(self):
        return json.dumps(self.to_dict())


class ActionRow(MessageComponent):
    _type = 1

    def __init__(self, *components):
        self.components = components

    def to_dict(self):
        data = {
            "type": self._type,
            "components": [comp.to_dict() for comp in self.components]
        }
        return data


class AwaitableComponent:
    interaction_type: InteractionType = None

    async def wait_for(self, timeout=None, check=None):
        from meta import client

        def _check(interaction):
            valid = True
            valid = valid and interaction.interaction_type == self.interaction_type
            valid = valid and interaction.custom_id == self.custom_id
            valid = valid and (check is None or check(interaction))
            return valid

        return await client.wait_for('interaction_create', timeout=timeout, check=_check)

    def add_callback(self, timeout=None, repeat=True, check=None, pass_args=(), pass_kwargs={}):
        def wrapper(func):
            async def _func(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except asyncio.CancelledError:
                    pass
                except asyncio.TimeoutError:
                    pass
                except Exception:
                    from meta import client
                    full_traceback = traceback.format_exc()

                    client.log(
                        f"Caught an unhandled exception while executing interaction callback "
                        f"for interaction type '{self.interaction_type.name}' with id '{self.custom_id}'.\n"
                        f"{self!r}\n"
                        f"{func!r}\n"
                        f"{full_traceback}",
                        context=f"cid:{self.custom_id}",
                        level=logging.ERROR
                    )

            async def wrapped():
                while True:
                    try:
                        button_press = await self.wait_for(timeout=timeout, check=check)
                    except asyncio.TimeoutError:
                        break
                    asyncio.create_task(_func(button_press, *pass_args, **pass_kwargs))
                    if not repeat:
                        break
            future = asyncio.create_task(wrapped())
            return future
        return wrapper


class Button(MessageComponent, AwaitableComponent):
    _type = 2

    def __init__(self, label, style=ButtonStyle.PRIMARY, custom_id=None, url=None, emoji=None, disabled=False):
        if style == ButtonStyle.LINK:
            if url is None:
                raise ValueError("Link buttons must have a url")
            custom_id = None
        elif custom_id is None:
            custom_id = str(uuid.uuid4())

        self.label = label
        self.style = style
        self.custom_id = custom_id
        self.url = url

        self.emoji = emoji
        self.disabled = disabled

    def to_dict(self):
        data = {
            "type": self._type,
            "label": self.label,
            "style": int(self.style)
        }
        if self.style == ButtonStyle.LINK:
            data['url'] = self.url
        else:
            data['custom_id'] = self.custom_id
        if self.emoji is not None:
            # TODO: This only supports PartialEmoji, not Emoji
            data['emoji'] = self.emoji.to_dict()
        if self.disabled:
            data['disabled'] = self.disabled
        return data


class SelectOption:
    def __init__(self, label, value, description, emoji=None, default=False):
        self.label = label
        self.value = value
        self.description = description
        self.emoji = emoji
        self.default = default

    def to_dict(self):
        data = {
            "label": self.label,
            "value": self.value,
            "description": self.description,
        }
        if self.emoji:
            data['emoji'] = self.emoji.to_dict()
        if self.default:
            data['default'] = self.default

        return data


class SelectMenu(MessageComponent, AwaitableComponent):
    _type = 3

    def __init__(self, *options, custom_id=None, placeholder=None, min_values=None, max_values=None, disabled=False):
        self.options = options
        self.custom_id = custom_id or str(uuid.uuid4())
        self.placeholder = placeholder
        self.min_values = min_values
        self.max_values = max_values
        self.disabled = disabled

    def set_default(self, value=None, index=None):
        """
        Convenience method to set the default option.
        """
        if index is not None and value is not None:
            raise ValueError("Both index and value were supplied for the default.")
        if index is not None:
            for i, option in enumerate(self.options):
                option.default = (i == index)
        elif value is not None:
            for option in self.options:
                option.default = (option.value == value)
        else:
            for option in self.options:
                option.default = False

    def to_dict(self):
        data = {
            "type": self._type,
            'custom_id': self.custom_id,
            'options': [option.to_dict() for option in self.options],
        }
        if self.placeholder:
            data['placeholder'] = self.placeholder
        if self.min_values:
            data['min_values'] = self.min_values
        if self.max_values:
            data['max_values'] = self.max_values
        if self.disabled:
            data['disabled'] = self.disabled
        return data
