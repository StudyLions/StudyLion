from settings import ModelData
from settings.groups import SettingGroup
from settings.setting_types import (
    ChannelSetting, RoleSetting,
)

from core.data import CoreData
from babel.translator import ctx_translator

from . import babel

_p = babel._p


class ModerationSettings(SettingGroup):
    class TicketLog(ModelData, ChannelSetting):
        setting_id = "ticket_log"
        _event = 'guildset_ticket_log'
        
        _display_name = _p('guildset:ticket_log', "ticket_log")
        _desc = _p(
            'guildset:ticket_log|desc',
            "Private moderation log to send tickets and moderation events."
        )
        _long_desc = _p(
            'guildset:ticket_log|long_desc',
            "Warnings, notes, video blacklists, and other moderation events "
            "will be posted as numbered tickets with context to this log."
        )
        _accepts = _p(
            'guildset:ticket_log|accepts',
            "Ticket channel name or id."
        )
        _default = None
        
        _model = CoreData.Guild
        _column = CoreData.Guild.mod_log_channel.name
        
        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'guildset:ticket_log|set_response:set',
                    "Moderation tickets will be sent to {channel}"
                )).format(channel=value.mention)
            else:
                resp = t(_p(
                    'guildset:ticket_log|set_response:unset',
                    "Moderation tickets will not be logged to a channel."
                ))
            return resp
        
        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            t = ctx_translator.get().t
            if data is not None:
                return super()._format_data(parent_id, data, **kwargs)
            else:
                return t(_p(
                    'guildset:ticket_log|formatted:unset',
                    "Not Set."
                ))

    class AlertChannel(ModelData, ChannelSetting):
        setting_id = "alert_channel"
        _event = 'guildset_alert_channel'
        
        _display_name = _p('guildset:alert_channel', "alert_channel")
        _desc = _p(
            'guildset:alert_channel|desc',
            "Moderation notification channel for members with DMs disabled."
        )
        _long_desc = _p(
            'guildset:alert_channel|long_desc',
            "When I need to send a member a moderation-related notification "
            "(e.g. asking them to enable their video in a video channel) "
            "from this server, I will try to send it via direct messages. "
            "If this fails, I will instead mention the user in this channel."
        )
        _accepts = _p(
            'guildset:alert_channel|accepts',
            "Alert channel name or id."
        )
        _default = None
        
        _model = CoreData.Guild
        _column = CoreData.Guild.alert_channel.name
        _allow_object = False
        
        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'guildset:alert_channel|set_response:set',
                    "Moderation alerts will be sent to {channel}"
                )).format(channel=value.mention)
            else:
                resp = t(_p(
                    'guildset:alert_channel|set_response:unset',
                    "Moderation alerts will be ignored if the member cannot be reached."
                ))
            return resp
        
        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            t = ctx_translator.get().t
            if data is not None:
                return super()._format_data(parent_id, data, **kwargs)
            else:
                return t(_p(
                    'guildset:alert_channel|formatted:unset',
                    "Not Set (Only alert via direct message.)"
                ))

    class ModRole(ModelData, RoleSetting):
        setting_id = "mod_role"
        _event = 'guildset_mod_role'
        
        _display_name = _p('guildset:mod_role', "mod_role")
        _desc = _p(
            'guildset:mod_role|desc',
            "Guild role permitted to view configuration and perform moderation tasks."
        )
        _long_desc = _p(
            'guildset:mod_role|long_desc',
            "Members with the set role will be able to access my configuration panels, "
            "and perform some moderation tasks, such us setting up pomodoro timers. "
            "Moderators cannot reconfigure most bot configuration, "
            "or perform operations they do not already have permission for in Discord."
        )
        _accepts = _p(
            'guildset:mod_role|accepts',
            "Moderation role name or id."
        )
        _default = None
        
        _model = CoreData.Guild
        _column = CoreData.Guild.mod_role.name
        
        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'guildset:mod_role|set_response:set',
                    "Members with the {role} will be considered moderators."
                )).format(role=value.mention)
            else:
                resp = t(_p(
                    'guildset:mod_role|set_response:unset',
                    "No members will be given moderation privileges."
                ))
            return resp
        
        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            t = ctx_translator.get().t
            if data is not None:
                return super()._format_data(parent_id, data, **kwargs)
            else:
                return t(_p(
                    'guildset:mod_role|formatted:unset',
                    "Not Set."
                ))
