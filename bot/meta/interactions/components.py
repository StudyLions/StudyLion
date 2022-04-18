import asyncio
import uuid

from .enums import ButtonStyle, InteractionType


"""
Notes:
    When interaction is sent, add message info
    Add wait_for to Button and SelectMenu
    wait_for_interaction for generic
    listen=True for the listenables, register with a listener
    Need a deregister then as well

    send(..., components=[ActionRow(Button(...))])

    Automatically ack interaction? DEFERRED_UPDATE_MESSAGE

    async def Button.wait_for(timeout=None, ack=False)
        Blocks until the button is pressed. Returns a ButtonPress (Interaction).
    def MessageComponent.add_callback(timeout)
        Adds an async callback function to the Component.

    Construct the response independent of the original component.
    Original component has a convenience wait_for that runs wait_for_interaction(custom_id=self.custom_id)...
    The callback? Just add a wait_for
"""


class MessageComponent:
    _type = None

    def __init_(self, *args, **kwargs):
        self.message = None

    def listen(self):
        ...

    def close(self):
        ...


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


class Button(MessageComponent):
    _type = 2

    def __init__(self, label, style=ButtonStyle.PRIMARY, custom_id=None, url=None, emoji=None, disabled=False):
        if style == ButtonStyle.LINK:
            if url is None:
                raise ValueError("Link buttons must have a url")
            custom_id = None
        elif custom_id is None:
            custom_id = uuid.uuid4()

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
        return data

    async def wait_for_press(self, timeout=None, check=None):
        from meta import client

        def _check(interaction):
            valid = True
            print(interaction.custom_id)
            valid = valid and interaction.interaction_type == InteractionType.MESSAGE_COMPONENT
            valid = valid and interaction.custom_id == self.custom_id
            valid = valid and (check is None or check(interaction))
            return valid

        return await client.wait_for('interaction_create', timeout=timeout, check=_check)

    def on_press(self, timeout=None, repeat=True, pass_args=(), pass_kwargs={}):
        def wrapper(func):
            async def wrapped():
                while True:
                    try:
                        button_press = await self.wait_for_press(timeout=timeout)
                    except asyncio.TimeoutError:
                        break
                    asyncio.create_task(func(button_press, *pass_args, **pass_kwargs))
                    if not repeat:
                        break
            future = asyncio.create_task(wrapped())
            return future
        return wrapper


class SelectMenu(MessageComponent):
    _type = 3


# MessageComponent listener
live_components = {}
