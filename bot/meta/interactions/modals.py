import uuid

from .enums import TextInputStyle, InteractionType
from .components import AwaitableComponent


class Modal(AwaitableComponent):
    interaction_type = InteractionType.MODAL_SUBMIT

    def __init__(self, title, *components, custom_id=None):
        self.custom_id = custom_id or str(uuid.uuid4())

        self.title = title
        self.components = components

    def to_dict(self):
        data = {
            'title': self.title,
            'custom_id': self.custom_id,
            'components': [comp.to_dict() for comp in self.components]
        }
        return data


class TextInput:
    _type = 4

    def __init__(
        self,
        label, placeholder=None, value=None, required=False,
        style=TextInputStyle.SHORT, min_length=None, max_length=None,
        custom_id=None
    ):
        self.custom_id = custom_id or str(uuid.uuid4())

        self.label = label
        self.placeholder = placeholder
        self.value = value
        self.required = required
        self.style = style
        self.min_length = min_length
        self.max_length = max_length

    def to_dict(self):
        data = {
            'type': self._type,
            'custom_id': self.custom_id,
            'style': int(self.style),
            'label': self.label,
        }
        for key in ('min_length', 'max_length', 'required', 'value', 'placeholder'):
            if (value := getattr(self, key)) is not None:
                data[key] = value
        return data
