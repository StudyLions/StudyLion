from typing import Any, Optional

import discord
from babel.translator import ctx_translator
from core.data import CoreData
from core.setting_types import MessageSetting
from meta import LionBot
from settings import ListData, ModelData
from settings.groups import SettingGroup
from settings.setting_types import BoolSetting, ChannelSetting, RoleListSetting
from utils.lib import recurse_map, replace_multiple, tabulate

from . import babel
from .data import MemberAdminData

_p = babel._p

_greeting_subkey_desc = {
    '{mention}': _p('guildset:greeting_message|formatkey:mention',
                    "Mention the new member."),
    '{user_name}': _p('guildset:greeting_message|formatkey:user_name',
                      "Display name of the new member."),
    '{user_avatar}': _p('guildset:greeting_message|formatkey:user_avatar',
                        "Avatar url of the new member."),
    '{guild_name}': _p('guildset:greeting_message|formatkey:guild_name',
                       "Name of this server."),
    '{guild_icon}': _p('guildset:greeting_message|formatkey:guild_icon',
                       "Server icon url."),
    '{studying_count}': _p('guildset:greeting_message|formatkey:studying_count',
                           "Number of current voice channel members."),
    '{member_count}': _p('guildset:greeting_message|formatkey:member_count',
                         "Number of members in the server."),
}


class MemberAdminSettings(SettingGroup):
    class GreetingChannel(ModelData, ChannelSetting):
        setting_id = 'greeting_channel'

        _display_name = _p('guildset:greeting_channel', "welcome_channel")
        _desc = _p(
            'guildset:greeting_channel|desc',
            "Channel in which to welcome new members to the server."
        )
        _long_desc = _p(
            'guildset:greeting_channel|long_desc',
            "New members will be sent the configured `welcome_message` in this channel, "
            "and returning members will be sent the configured `returning_message`. "
            "Unset to send these message via direct message."
        )
        _accepts = _p(
            'guildset:greeting_channel|accepts',
            "Name or id of the greeting channel, or 0 for DM."
        )

        _model = CoreData.Guild
        _column = CoreData.Guild.greeting_channel.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value is None:
                # Greetings will be sent via DM
                resp = t(_p(
                    'guildset:greeting_channel|set_response:unset',
                    "Welcome messages will now be sent via direct message."
                ))
            else:
                resp = t(_p(
                    'guildset:greeting_channel|set_response:set',
                    "Welcome messages will now be sent to {channel}"
                )).format(channel=value.mention)
            return resp

        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            t = ctx_translator.get().t
            if data is not None:
                return f"<#{data}>"
            else:
                return t(_p(
                    'guildset:greeting_channel|formmatted:unset',
                    "Direct Message"
                ))

    class GreetingMessage(ModelData, MessageSetting):
        setting_id = 'greeting_message'

        _display_name = _p(
            'guildset:greeting_message', "welcome_message"
        )
        _desc = _p(
            'guildset:greeting_message|desc',
            "Custom message used to greet new members when they join the server."
        )
        _long_desc = _p(
            'guildset:greeting_message|long_desc',
            "When set, this message will be sent to the `welcome_channel` when a *new* member joins the server. "
            "If not set, no message will be sent."
        )
        _accepts = _p(
            'guildset:greeting_message|accepts',
            "JSON formatted greeting message data"
        )
        _soft_default = _p(
            'guildset:greeting_message|default',
            r"""
            {
                "embed": {
                    "title": "Welcome {user_name}!",
                    "thumbnail": {"url": "{user_avatar}"},
                    "description": "Welcome to **{guild_name}**!",
                    "footer": {
                        "text": "You are the {member_count}th member!"
                    },
                    "color": 15695665
                },
            }
            """
        )

        _model = CoreData.Guild
        _column = CoreData.Guild.greeting_message.name

        _subkey_desc = _greeting_subkey_desc

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value is None:
                # No greetings
                resp = t(_p(
                    'guildset:greeting_message|set_response:unset',
                    "Welcome message unset! New members will not be greeted."
                ))
            else:
                resp = t(_p(
                    'guildset:greeting_message|set_response:set',
                    "The welcome message has been updated."
                ))
            return resp

        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            t = ctx_translator.get().t
            if data is not None:
                return super()._format_data(parent_id, data, **kwargs)
            else:
                return t(_p(
                    'guildset:greeting_message|formmatted:unset',
                    "Not set, members will not be welcomed."
                ))

        @classmethod
        async def generate_formatter(cls, bot: LionBot, member: discord.Member, **kwargs):
            """
            Generate a formatter function for this message from the given context.

            The formatter function both accepts and returns a message data dict.
            """
            async def formatter(data_dict: Optional[dict[str, Any]]):
                if not data_dict:
                    return None

                guild = member.guild
                active = sum(1 for ch in guild.voice_channels for member in ch.members)
                mapping = {
                    '{mention}': member.mention,
                    '{user_name}': member.display_name,
                    '{user_avatar}': member.avatar.url if member.avatar else member.default_avatar.url,
                    '{guild_name}': guild.name,
                    '{guild_icon}': guild.icon.url if guild.icon else member.default_avatar.url,
                    '{studying_count}': str(active),
                    '{member_count}': len(guild.members),
                }

                recurse_map(
                    lambda loc, value: replace_multiple(value, mapping) if isinstance(value, str) else value,
                    data_dict,
                )

                return data_dict
            return formatter

        async def editor_callback(self, editor_data):
            self.value = editor_data
            await self.write()

        def _desc_table(self) -> list[str]:
            lines = super()._desc_table()
            t = ctx_translator.get().t
            keydescs = [
                (key, t(value)) for key, value in self._subkey_desc.items()
            ]
            keytable = tabulate(*keydescs, colon='')
            expline = t(_p(
                'guildset:greeting_message|embed_field|formatkeys|explanation',
                "The following placeholders will be substituted with their values."
            ))
            keyfield = (
                t(_p('guildset:greeting_message|embed_field|formatkeys|name', "Placeholders")),
                expline + '\n' + '\n'.join(f"> {line}" for line in keytable)
            )
            lines.append(keyfield)
            return lines

    class ReturningMessage(ModelData, MessageSetting):
        setting_id = 'returning_message'

        _display_name = _p(
            'guildset:returning_message', "returning_message"
        )
        _desc = _p(
            'guildset:returning_message|desc',
            "Custom message used to greet returning members when they rejoin the server."
        )
        _long_desc = _p(
            'guildset:returning_message|long_desc',
            "When set, this message will be sent to the `welcome_channel` when a member *returns* to the server. "
            "If not set, no message will be sent."
        )
        _accepts = _p(
            'guildset:returning_message|accepts',
            "JSON formatted returning message data"
        )
        _soft_default = _p(
            'guildset:returning_message|default',
            r"""
            {
                "embed": {
                    "title": "Welcome Back {user_name}!",
                    "thumbnail": {"url": "{User_avatar}"},
                    "description": "Welcome back to **{guild_name}**!\nYou were last seen <t:{last_time}:R>.",
                    "color": 15695665
                }
            }
            """
        )

        _model = CoreData.Guild
        _column = CoreData.Guild.returning_message.name

        _subkey_desc_returning = {
            '{last_time}': _p('guildset:returning_message|formatkey:last_time',
                              "Unix timestamp of the last time the member was seen in the server.")
        }
        _subkey_desc = _greeting_subkey_desc | _subkey_desc_returning

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value is None:
                resp = t(_p(
                    'guildset:returning_message|set_response:unset',
                    "Returning member greeting unset! Will use `welcome_message` if set."
                ))
            else:
                resp = t(_p(
                    'guildset:greeting_message|set_response:set',
                    "The returning member greeting has been updated."
                ))
            return resp

        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            t = ctx_translator.get().t
            if data is not None:
                return super()._format_data(parent_id, data, **kwargs)
            else:
                return t(_p(
                    'guildset:greeting_message|formmatted:unset',
                    "Not set, will use the `welcome_message` if set."
                ))

        @classmethod
        async def generate_formatter(cls, bot: LionBot,
                                     member: discord.Member, last_seen: Optional[int],
                                     **kwargs):
            """
            Generate a formatter function for this message from the given context.

            The formatter function both accepts and returns a message data dict.
            """
            async def formatter(data_dict: Optional[dict[str, Any]]):
                if not data_dict:
                    return None

                guild = member.guild
                active = sum(1 for ch in guild.voice_channels for member in ch.members)
                mapping = {
                    '{mention}': member.mention,
                    '{user_name}': member.display_name,
                    '{user_avatar}': member.avatar.url if member.avatar else member.default_avatar.url,
                    '{guild_name}': guild.name,
                    '{guild_icon}': guild.icon.url if guild.icon else member.default_avatar.url,
                    '{studying_count}': str(active),
                    '{member_count}': str(len(guild.members)),
                    '{last_time}': str(last_seen or member.joined_at.timestamp()),
                }

                recurse_map(
                    lambda loc, value: replace_multiple(value, mapping) if isinstance(value, str) else value,
                    data_dict,
                )

                return data_dict
            return formatter

        async def editor_callback(self, editor_data):
            self.value = editor_data
            await self.write()

        def _desc_table(self) -> list[str]:
            lines = super()._desc_table()
            t = ctx_translator.get().t
            keydescs = [
                (key, t(value)) for key, value in self._subkey_desc_returning.items()
            ]
            keytable = tabulate(*keydescs, colon='')
            expline = t(_p(
                'guildset:returning_message|embed_field|formatkeys|explanation',
                "In *addition* to the placeholders supported by `welcome_message`"
            ))
            keyfield = (
                t(_p('guildset:returning_message|embed_field|formatkeys|', "Placeholders")),
                expline + '\n' + '\n'.join(f"> {line}" for line in keytable)
            )
            lines.append(keyfield)
            return lines


    class Autoroles(ListData, RoleListSetting):
        setting_id = 'autoroles'

        _display_name = _p(
            'guildset:autoroles', "autoroles"
        )
        _desc = _p(
            'guildset:autoroles|desc',
            "Roles given to new members when they join the server."
        )
        _long_desc = _p(
            'guildset:autoroles|long_desc',
            "These roles will be given when a member joins the server. "
            "If `role_persistence` is enabled, these roles will *not* be given to a returning member."
        )

        _table_interface = MemberAdminData.autoroles
        _id_column = 'guildid'
        _data_column = 'roleid'
        _order_column = 'roleid'


    class BotAutoroles(ListData, RoleListSetting):
        setting_id = 'bot_autoroles'

        _display_name = _p(
            'guildset:bot_autoroles', "bot_autoroles"
        )
        _desc = _p(
            'guildset:bot_autoroles|desc',
            "Roles given to new bots when they join the server."
        )
        _long_desc = _p(
            'guildset:bot_autoroles|long_desc',
            "These roles will be given when a bot joins the server."
        )


        _table_interface = MemberAdminData.bot_autoroles
        _id_column = 'guildid'
        _data_column = 'roleid'
        _order_column = 'roleid'

    class RolePersistence(ModelData, BoolSetting):
        setting_id = 'role_persistence'
        _event = 'guildset_role_persistence'

        _display_name = _p('guildset:role_persistence', "role_persistence")
        _desc = _p(
            'guildset:role_persistence|desc',
            "Whether member roles should be restored on rejoin."
        )
        _long_desc = _p(
            'guildset:role_persistence|long_desc',
            "If enabled, member roles will be stored when they leave the server, "
            "and then restored when they rejoin (instead of giving `autoroles`). "
            "Note that this may conflict with other bots who manage join roles."
        )
        _default = True

        _model = CoreData.Guild
        _column = CoreData.Guild.persist_roles.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if not value:
                resp = t(_p(
                    'guildset:role_persistence|set_response:off',
                    "Roles will not be restored when members rejoin."
                ))
            else:
                resp = t(_p(
                    'guildset:greeting_message|set_response:on',
                    "Roles will now be restored when members rejoin."
                ))
            return resp

    guild_model_settings = (
        GreetingChannel,
        GreetingMessage,
        ReturningMessage,
        RolePersistence,
    )
