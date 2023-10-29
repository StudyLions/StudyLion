from typing import Optional
from dataclasses import dataclass, field

import uuid
import discord
from discord.components import SelectOption

from babel.translator import LazyStr
from gui.base.Card import Card
from utils.lib import EmbedField, tabulate

from .skinsetting import SettingInputType, Setting
from ..skinlib import CustomSkin


@dataclass
class SettingGroup:
    """
    Data class representing a collection of settings which are naturally
    grouped together at interface level.

    Typically the settings in a single SettingGroup are displayed
    in the same embed field, the settings are edited with the same modal,
    and the group represents a single option in the "setting group menu".

    Setting groups do not correspond to any grouping at the Card or Skin level,
    and may cross multiple cards.
    """

    # The name and description strings are shown in the embed field and menu option
    name: LazyStr

    # Tuple of settings that are part of this setting group
    settings: tuple[Setting, ...]

    description: Optional[LazyStr] = None

    # Whether the group should be displayed in a group or not
    ungrouped: bool = False

    # Whether the embed field should be inline 
    inline: bool = True

    # Component custom id to identify the editing component
    # Also used as the value of the select option
    custom_id: str = str(uuid.uuid4())

    @property
    def editable_settings(self):
        return tuple(setting for setting in self.settings if setting.input_type is SettingInputType.ModalInput)

    def embed_field_for(self, skin: CustomSkin) -> EmbedField:
        """
        Tabulates the contained settings and builds an embed field for the editor UI.
        """
        t = skin.bot.translator.t

        rows: list[tuple[str, str]] = []
        for setting in self.settings:
            name = t(setting.display_name)
            value = setting.value_in(skin) or setting.default_value_in(skin)
            formatted = setting.format_value_in(skin, value)
            rows.append((name, formatted))

        lines = tabulate(*rows)
        table = '\n'.join(lines)

        description = f"*{t(self.description)}*" if self.description else ''

        embed_field = EmbedField(
            name=t(self.name),
            value=f"{description}\n{table}",
            inline=self.inline,
        )
        return embed_field

    def select_option_for(self, skin: CustomSkin) -> SelectOption:
        """
        Makes a SelectOption referring to this setting group.
        """
        t = skin.bot.translator.t
        option = SelectOption(
            label=t(self.name),
            description=t(self.description) if self.description else None,
            value=self.custom_id,
        )
        return option


@dataclass
class Page:
    """
    Represents a page of skin settings for the skin editor UI.
    """
    # Various string attributes of the page
    display_name: LazyStr
    editing_description: Optional[LazyStr] = None
    preview_description: Optional[LazyStr] = None

    visible_in_preview: bool = True
    render_card: Optional[type[Card]] = None

    groups: list[SettingGroup] = field(default_factory=list)

    def make_embed_for(self, skin: CustomSkin) -> discord.Embed:
        t = skin.bot.translator.t

        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title=t(self.display_name),
        )

        description_lines: list[str] = []
        field_counter = 0

        for group in self.groups:
            field = group.embed_field_for(skin)
            if group.ungrouped:
                description_lines.append(field.value)
            else:
                embed.add_field(**field._asdict())
                if not (field_counter) % 3:
                    embed.add_field(name='', value='')
                    field_counter += 1
                field_counter += 1

        if description_lines:
            embed.description = '\n'.join(description_lines)

        if self.render_card is not None:
            embed.set_image(url='attachment://sample.png')

        return embed
