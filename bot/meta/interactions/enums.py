from enum import IntEnum


class InteractionType(IntEnum):
    PING = 1
    APPLICATION_COMMAND = 2
    MESSAGE_COMPONENT = 3
    APPLICATION_COMMAND_AUTOCOMPLETE = 4
    MODAL_SUBMIT = 5


class ComponentType(IntEnum):
    ACTIONROW = 1
    BUTTON = 2
    SELECTMENU = 3
    TEXTINPUT = 4


class ButtonStyle(IntEnum):
    PRIMARY = 1
    SECONDARY = 2
    SUCCESS = 3
    DANGER = 4
    LINK = 5


class InteractionCallback(IntEnum):
    DEFERRED_UPDATE_MESSAGE = 6
