from utils.lib import DotDict
from wards import guild_admin
from settings import ObjectSettings, ColumnData, Setting
import settings.setting_types as setting_types

from .data import reaction_role_messages, reaction_role_reactions


class RoleMessageSettings(ObjectSettings):
    settings = DotDict()


class RoleMessageSetting(ColumnData, Setting):
    _table_interface = reaction_role_messages
    _id_column = 'messageid'
    _create_row = False

    write_ward = guild_admin


@RoleMessageSettings.attach_setting
class required_role(setting_types.Role, RoleMessageSetting):
    attr_name = 'required_role'
    _data_column = 'required_role'

    display_name = "required_role"
    desc = "Role required to use the reaction roles."

    long_desc = (
        "Members will be required to have the specified role to use the reactions on this message."
    )

    @property
    def success_response(self):
        if self.value:
            return "Members need {} to use these reaction roles.".format(self.formatted)
        else:
            return "All members can now use these reaction roles."

    @classmethod
    def _get_guildid(cls, id: int, **kwargs):
        return reaction_role_messages.fetch(id).guildid


@RoleMessageSettings.attach_setting
class removable(setting_types.Boolean, RoleMessageSetting):
    attr_name = 'removable'
    _data_column = 'removable'

    display_name = "removable"
    desc = "Whether the role is removable by deselecting the reaction."

    long_desc = (
        "If enabled, the role will be removed when the reaction is deselected."
    )

    _default = True

    @property
    def success_response(self):
        if self.value:
            return "Members will be able to remove roles by unreacting."
        else:
            return "Members will not be able to remove the reaction roles."


@RoleMessageSettings.attach_setting
class maximum(setting_types.Integer, RoleMessageSetting):
    attr_name = 'maximum'
    _data_column = 'maximum'

    display_name = "maximum"
    desc = "The maximum number of roles a member can get from this message."

    long_desc = (
        "The maximum number of roles that a member can get from this message. "
        "They will be notified by DM if they attempt to add more.\n"
        "The `removable` setting should generally be enabled with this setting."
    )

    accepts = "An integer number of roles, or `None` to remove the maximum."

    _min = 0

    @classmethod
    def _format_data(cls, id, data, **kwargs):
        if data is None:
            return "No maximum!"
        else:
            return "`{}`".format(data)

    @property
    def success_response(self):
        if self.value:
            return "Members can get a maximum of `{}` roles from this message.".format(self.value)
        else:
            return "Members can now get all the roles from this mesage."


@RoleMessageSettings.attach_setting
class refunds(setting_types.Boolean, RoleMessageSetting):
    attr_name = 'refunds'
    _data_column = 'refunds'

    display_name = "refunds"
    desc = "Whether a user will be refunded when they deselect a role."

    long_desc = (
        "Whether to give the user a refund when they deselect a role by reaction. "
        "This has no effect if `removable` is not enabled, or if the role removed has no cost."
    )

    _default = True

    @property
    def success_response(self):
        if self.value:
            return "Members will get a refund when they remove a role."
        else:
            return "Members will not get a refund when they remove a role."


@RoleMessageSettings.attach_setting
class default_price(setting_types.Integer, RoleMessageSetting):
    attr_name = 'default_price'
    _data_column = 'default_price'

    display_name = "default_price"
    desc = "Default price of reaction roles on this message."

    long_desc = (
        "Reaction roles on this message will have this cost if they do not have an individual price set."
    )

    accepts = "An integer number of coins. Use `0` or `None` to make roles free by default."

    _default = 0

    @classmethod
    def _format_data(cls, id, data, **kwargs):
        if not data:
            return "Free"
        else:
            return "`{}` coins".format(data)

    @property
    def success_response(self):
        if self.value:
            return "Reaction roles on this message will cost `{}` coins by default.".format(self.value)
        else:
            return "Reaction roles on this message will be free by default."


@RoleMessageSettings.attach_setting
class log(setting_types.Boolean, RoleMessageSetting):
    attr_name = 'log'
    _data_column = 'event_log'

    display_name = "log"
    desc = "Whether to log reaction role usage in the event log."

    long_desc = (
        "When enabled, roles added or removed with reactions will be logged in the configured event log."
    )

    _default = True

    @property
    def success_response(self):
        if self.value:
            return "Role updates will now be logged."
        else:
            return "Role updates will not be logged."


class ReactionSettings(ObjectSettings):
    settings = DotDict()


class ReactionSetting(ColumnData, Setting):
    _table_interface = reaction_role_reactions
    _id_column = 'reactionid'
    _create_row = False

    write_ward = guild_admin


@ReactionSettings.attach_setting
class price(setting_types.Integer, ReactionSetting):
    attr_name = 'price'
    _data_column = 'price'

    display_name = "price"
    desc = "Price of this reaction role."

    long_desc = (
        "The number of coins that will be deducted from the user when this reaction is used.\n"
        "The number may be negative, in order to give a reward when the member choses the reaction."
    )

    accepts = "An integer number of coins. Use `0` to make the role free, or `None` to use the message default."

    @property
    def default(self):
        """
        The default price is given by the ReactionMessage price setting.
        """
        return default_price.get(self._table_interface.fetch(self.id).messageid).value

    @classmethod
    def _format_data(cls, id, data, **kwargs):
        if not data:
            return "Free"
        else:
            return "`{}` coins".format(data)

    @property
    def success_response(self):
        if self.value is not None:
            return "{{reaction.emoji}} {{reaction.role.mention}} now costs `{}` coins.".format(self.value)
        else:
            return "{reaction.emoji} {reaction.role.mention} is now free."


@ReactionSettings.attach_setting
class timeout(setting_types.Duration, ReactionSetting):
    attr_name = 'timeout'
    _data_column = 'timeout'

    display_name = "timeout"
    desc = "How long this reaction role will last."

    long_desc = (
        "If set, the reaction role will be removed after the configured duration. "
        "Note that this does not affect existing members with the role, or existing expiries."
    )

    _default_multiplier = 1

    @classmethod
    def _format_data(cls, id, data, **kwargs):
        if data is None:
            return "Never"
        else:
            return super()._format_data(id, data, **kwargs)

    @property
    def success_response(self):
        if self.value is not None:
            return "{{reaction.emoji}} {{reaction.role.mention}} will timeout `{}` after selection.".format(
                self.formatted
            )
        else:
            return "{reaction.emoji} {reaction.role.mention} will never timeout after selection."
