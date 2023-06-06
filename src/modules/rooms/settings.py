from settings import ModelData
from settings.groups import SettingGroup
from settings.setting_types import ChannelSetting, IntegerSetting, BoolSetting

from meta import conf
from core.data import CoreData
from babel.translator import ctx_translator

from . import babel

_p = babel._p


class RoomSettings(SettingGroup):
    class Category(ModelData, ChannelSetting):
        setting_id = 'rooms_category'
        _event = 'guildset_rooms_category'
        _set_cmd = 'configure rooms'

        _display_name = _p(
            'guildset:room_category', "rooms_category"
        )
        _desc = _p(
            'guildset:rooms_category|desc',
            "Category in which to create private voice channels."
        )
        _long_desc = _p(
            'guildset:room_category|long_desc',
            "When a member uses `/room rent` to rent a new private room, "
            "a private voice channel will be created under this category, "
            "manageable by the member. "
            "I must have permission to create new channels in this category, "
            "as well as to manage permissions."
        )
        _accepts = _p(
            'guildset:room_category|accepts',
            "Private room category name or id."
        )

        _model = CoreData.Guild
        _column = CoreData.Guild.renting_category.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value is None:
                # Shut down renting system
                resp = t(_p(
                    'guildset:rooms_category|set_response:unset',
                    "The private room category has been unset. Existing private rooms will not be affected. "
                    "Delete the channels manually to remove the private rooms."
                ))
            else:
                resp = t(_p(
                    'guildset:rooms_category|set_response:set',
                    "Private room category has been set to {channel}. Existing private rooms will be moved."
                )).format(channel=self.value.mention)
            return resp

        @property
        def set_str(self) -> str:
            cmdstr = super().set_str
            t = ctx_translator.get().t
            return t(_p(
                'guildset:room_category|set_using',
                "{cmd} or category selector below."
            )).format(cmd=cmdstr)

    class Rent(ModelData, IntegerSetting):
        setting_id = 'rooms_price'
        _event = 'guildset_rooms_price'
        _set_cmd = 'configure rooms'

        _display_name = _p(
            'guildset:rooms_price', "room_rent"
        )
        _desc = _p(
            'guildset:rooms_rent|desc',
            "Daily rent price for a private room."
        )
        _long_desc = _p(
            'guildset:rooms_rent|long_desc',
            "Members will be charged this many LionCoins for each day they rent a private room."
        )
        _accepts = _p(
            'guildset:rooms_rent|accepts',
            "Number of LionCoins charged per day for a private room."
        )
        _default = 1000

        _model = CoreData.Guild
        _column = CoreData.Guild.renting_price.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            resp = t(_p(
                'guildset:rooms_price|set_response',
                "Private rooms will now cost {coin}**{amount}}** per 24 hours."
            )).format(
                coin=conf.emojis.coin,
                amount=self.value
            )
            return resp

    class MemberLimit(ModelData, IntegerSetting):
        setting_id = 'rooms_slots'
        _event = 'guildset_rooms_slots'
        _set_cmd = 'configure rooms'

        _display_name = _p('guildset:rooms_slots', "room_member_cap")
        _desc = _p(
            'guildset:rooms_slots|desc',
            "Maximum number of members in each private room."
        )
        _long_desc = _p(
            'guildset:rooms_slots|long_desc',
            "Private room owners may invite other members to their private room via the UI, "
            "or through the `/room invite` command. "
            "This setting limits the maximum number of members a private room may hold."
        )
        _accepts = _p(
            'guildset:rooms_slots|accepts',
            "Maximum number of members allowed per private room."
        )
        _default = 25

        _model = CoreData.Guild
        _column = CoreData.Guild.renting_cap.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            resp = t(_p(
                'guildset:rooms_slots|set_response',
                "Private rooms are now capped to **{amount}** members."
            )).format(amount=self.value)
            return resp

    class Visible(ModelData, BoolSetting):
        setting_id = 'rooms_visible'
        _event = 'guildset_rooms_visible'
        _set_cmd = 'configure rooms'

        _display_name = _p('guildset:rooms_visible', "room_visibility")
        _desc = _p(
            'guildset:rooms_visible|desc',
            "Whether private rented rooms are visible to non-members."
        )
        _long_desc = _p(
            'guildset:rooms_visible|long_desc',
            "If enabled, new private rooms will be created with the `VIEW_CHANNEL` permission "
            "enabled for the `@everyone` role."
        )
        _default = False
        _accepts = _p('guildset:rooms_visible|accepts', "Visible/Invisible")
        _outputs = {
            True: _p('guildset:rooms_visible|output:true', "Visible"),
            False: _p('guildset:rooms_visible|output:false', "Invisible"),
        }
        _outputs[None] = _outputs[_default]

        _truthy = _p(
            'guildset:rooms_visible|parse:truthy_values',
            "visible|enabled|yes|true|on|enable|1"
        )
        _falsey = _p(
            'guildset:rooms_visible|parse:falsey_values',
            'invisible|disabled|no|false|off|disable|0'
        )

        _model = CoreData.Guild
        _column = CoreData.Guild.renting_visible.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            if self.value:
                resp = t(_p(
                    'guildset:rooms_visible|set_response:enabled',
                    "Private rooms will now be visible to everyone."
                ))
            else:
                resp = t(_p(
                    'guildset:rooms_visible|set_response:disabled',
                    "Private rooms will now only be visible to their members (and admins)."
                ))
            return resp

        @property
        def set_str(self) -> str:
            cmdstr = super().set_str
            t = ctx_translator.get().t
            return t(_p(
                'guildset:rooms_visible|set_using',
                "{cmd} or toggle below."
            )).format(cmd=cmdstr)

    model_settings = (
        Category,
        Rent,
        MemberLimit,
        Visible,
    )
