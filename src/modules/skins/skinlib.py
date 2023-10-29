from collections import defaultdict
from typing import Optional

from frozendict import frozendict
import discord
from discord.components import SelectOption
from discord.app_commands import Choice

from gui.base import AppSkin
from meta import LionBot
from meta.logger import log_wrap

from .data import CustomSkinData


def appskin_as_option(skin: AppSkin) -> SelectOption:
    """
    Create a SelectOption from the given localised AppSkin
    """
    return SelectOption(
        label=skin.display_name,
        description=skin.description,
        value=skin.skin_id,
    )


def appskin_as_choice(skin: AppSkin) -> Choice[str]:
    """
    Create an appcmds.Choice from the given localised AppSkin
    """
    return Choice(
        name=skin.display_name,
        value=skin.skin_id,
    )


class FrozenCustomSkin:
    __slots__ = ('base_skin_name', 'properties')

    def __init__(self, base_skin_name: Optional[str], properties: dict[str, dict[str, str]]):
        self.base_skin_name = base_skin_name
        self.properties = frozendict((card, frozendict(props)) for card, props in properties.items())

    def args_for(self, card_id: str):
        args = {}
        if self.base_skin_name is not None:
            args["base_skin_id"] = self.base_skin_name
            if card_id in self.properties:
                args.update(self.properties[card_id])
        return args


class CustomSkin:
    def __init__(self,
        bot: LionBot,
        base_skin_name: Optional[str]=None,
        properties: dict[str, dict[str, str]] = {},
        data: Optional[CustomSkinData.CustomisedSkin]=None,
    ):
        self.bot = bot
        self.data = data

        self.base_skin_name = base_skin_name
        self.properties = properties

    @property
    def cog(self):
        return self.bot.get_cog('CustomSkinCog')

    @property
    def skinid(self) -> Optional[int]:
        return self.data.custom_skin_id if self.data else None

    @property
    def base_skin_id(self) -> Optional[int]:
        if self.base_skin_name is not None:
            return self.cog.appskin_names.inverse[self.base_skin_name]

    @classmethod
    async def fetch(cls, bot: LionBot, skinid: int) -> Optional['CustomSkin']:
        """
        Fetch the specified skin from data.
        """
        cog = bot.get_cog('CustomSkinCog')
        row = await cog.data.CustomisedSkin.fetch(skinid)
        if row is not None:
            records = await cog.data.custom_skin_info.select_where(
                custom_skin_id=skinid
            )
            properties = defaultdict(dict)
            for record in records:
                card_id = record['card_id']
                prop_name = record['property_name']
                prop_value = record['value']
                properties[card_id][prop_name] = prop_value
            if row.base_skin_id is not None:
                base_skin_name = cog.appskin_names[row.base_skin_id]
            else:
                base_skin_name = None
            self = cls(bot, base_skin_name, properties, data=row)
            return self

    @log_wrap(action='Save Skin')
    async def save(self):
        if self.data is None:
            raise ValueError("Cannot save a dataless CustomSkin")

        async with self.bot.db.connection() as conn:
            self.bot.db.conn = conn
            async with conn.transaction():
                skinid = self.skinid
                await self.data.update(base_skin_id=self.base_skin_id)
                await self.cog.data.skin_properties.delete_where(custom_skin_id=skinid)

                props = {
                    (card, name): value
                    for card, card_props in self.properties.items()
                    for name, value in card_props.items()
                    if value is not None
                }
                # Ensure the properties exist in cache
                await self.cog.fetch_property_ids(*props.keys())

                # Now bulk insert
                if props:
                    await self.cog.data.skin_properties.insert_many(
                        ('custom_skin_id', 'property_id', 'value'),
                        *(
                            (skinid, self.cog.skin_properties.inverse[propkey], value)
                            for propkey, value in props.items()
                        )
                    )
        await self.bot.global_dispatch('skin_updated', skinid)

    def get_prop(self, card_id: str, prop_name: str) -> Optional[str]:
        return self.properties.get(card_id, {}).get(prop_name, None)

    def set_prop(self, card_id: str, prop_name: str, value: Optional[str]):
        cardprops = self.properties.get(card_id, None)
        if value is None:
            if cardprops is not None:
                cardprops.pop(prop_name, None)
        else:
            if cardprops is None:
                cardprops = self.properties[card_id] = {}
            cardprops[prop_name] = value

    def resolve_propid(self, propid: int) -> tuple[str, str]:
        return self.cog.skin_properties[propid]

    def __getitem__(self, propid: int) -> Optional[str]:
        return self.get_prop(*self.resolve_propid(propid))

    def __setitem__(self, propid: int, value: Optional[str]):
        return self.set_prop(*self.resolve_propid(propid), value)

    def __delitem__(self, propid: int):
        card, name = self.resolve_propid(propid)
        self.properties.get(card, {}).pop(name, None)

    def freeze(self) -> FrozenCustomSkin:
        """
        Freeze the custom skin data into a memory efficient FrozenCustomSkin.
        """
        return FrozenCustomSkin(self.base_skin_name, self.properties)

    def load_frozen(self, frozen: FrozenCustomSkin):
        """
        Update state from the given frozen state.
        """
        self.base_skin_name = frozen.base_skin_name
        self.properties = dict((card, dict(props)) for card, props in frozen.properties.items())
        return self

    def args_for(self, card_id: str):
        args = {}
        if self.base_skin_name is not None:
            args["base_skin_id"] = self.base_skin_name
            if card_id in self.properties:
                args.update(self.properties[card_id])
        return args
