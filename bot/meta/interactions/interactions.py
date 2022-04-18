import asyncio
from .enums import ComponentType, InteractionType, InteractionCallback


class Interaction:
    __slots__ = (
        'id',
        'token',
        '_state'
    )

    async def callback_deferred(self):
        return await self._state.http.interaction_callback(self.id, self.token, InteractionCallback.DEFERRED_UPDATE_MESSAGE)

    def ack(self):
        asyncio.create_task(self.callback_deferred())


class ComponentInteraction(Interaction):
    interaction_type = InteractionType.MESSAGE_COMPONENT
    # TODO: Slots

    def __init__(self, message, user, data, state):
        self.message = message
        self.user = user

        self._state = state

        self._from_data(data)

    def _from_data(self, data):
        self.id = data['id']
        self.token = data['token']
        self.application_id = data['application_id']

        component_data = data['data']

        self.component_type = ComponentType(component_data['component_type'])
        self.custom_id = component_data.get('custom_id', None)


class ButtonPress(ComponentInteraction):
    __slots__ = ()


class Selection(ComponentInteraction):
    __slots__ = ('values',)

    def _from_data(self, data):
        super()._from_data(data)
        self.values = data['data']['values']


def _component_interaction_factory(data):
    component_type = data['data']['component_type']

    if component_type == ComponentType.BUTTON:
        return ButtonPress
    elif component_type == ComponentType.SELECTMENU:
        return Selection
    else:
        return None
