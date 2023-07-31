import discord
from discord.ui.select import SelectOption
from discord.app_commands import Choice

from utils.lib import MessageArgs
from babel.translator import ctx_translator

from . import babel

_p = babel._p


DEFAULT_EMOJI = '🔲'


templates = {}


class Template:
    def __init__(self, id, name, description, formatter):
        self.id = id
        self.name = name
        self.description = description
        self.formatter = formatter

    def as_option(self) -> SelectOption:
        # Select options need to be strings, so we localise
        t = ctx_translator.get().t
        name = t(self.name)
        description = t(self.description)
        return SelectOption(label=name, value=str(self.id), description=description)

    def as_choice(self) -> Choice[int]:
        # Appcmd choices are allowed to be LazyStrings, so we don't localise
        return Choice(name=self.name, value=self.id)

    async def render_menu(self, menu) -> MessageArgs:
        # TODO: Some error catching and logging might be good here
        return await self.formatter(menu)


def register_template(id, name, description):
    def wrapper(coro):
        template = Template(id, name, description, coro)
        templates[id] = template
        return template
    return wrapper


@register_template(
    id=0,
    name=_p(
        'template:simple|name', "Simple Menu"
    ),
    description=_p(
        'template:simple|desc',
        "A simple embedded list of roles in the menu"
    )
)
async def simple_template(menu) -> MessageArgs:
    menuroles = menu.roles
    lines = []
    for menurole in menuroles:
        parts = []
        emoji = menurole.config.emoji
        role = menurole.config.role
        price = menurole.config.price
        duration = menurole.config.duration

        if emoji.data:
            parts.append(emoji.formatted)

        parts.append(role.formatted)

        if price.data:
            parts.append(f"({price.formatted})")

        if duration.data:
            parts.append(f"({duration.formatted})")

        lines.append(' '.join(parts))

    description = '\n'.join(lines)

    embed = discord.Embed(
        title=menu.config.name.value,
        description=description,
        colour=discord.Colour.orange()
    )
    return MessageArgs(embed=embed)


@register_template(
    id=1,
    name=_p(
        'template:two_column|name', "Two Column"
    ),
    description=_p(
        'template:two_column|desc',
        "A compact two column role layout. Excludes prices and durations."
    )
)
async def twocolumn_template(menu) -> MessageArgs:
    menuroles = menu.roles

    count = len(menuroles)
    split_at = count // 2

    blocks = (menuroles[:split_at], menuroles[split_at:])

    embed = discord.Embed(
        title=menu.config.name.value,
        colour=discord.Colour.orange()
    )
    for block in blocks:
        block_lines = [
            f"{menurole.config.emoji.formatted or DEFAULT_EMOJI} {menurole.config.label.formatted}"
            for menurole in block
        ]
        if block_lines:
            embed.add_field(
                name='',
                value='\n'.join(block_lines)
            )
    return MessageArgs(embed=embed)


@register_template(
    id=2,
    name=_p(
        'template:three_column|name', "Three Column"
    ),
    description=_p(
        'template:three_column|desc',
        "A compact three column layout using emojis and labels, excluding prices and durations."
    )
)
async def threecolumn_template(menu) -> MessageArgs:
    menuroles = menu.roles

    count = len(menuroles)
    split_at = count // 3
    if count % 3 == 2:
        split_at += 1

    blocks = (menuroles[:split_at], menuroles[split_at:2*split_at], menuroles[2*split_at:])

    embed = discord.Embed(
        title=menu.config.name.value,
        colour=discord.Colour.orange()
    )
    for block in blocks:
        block_lines = [
            f"{menurole.config.emoji.formatted or DEFAULT_EMOJI} {menurole.config.label.formatted}"
            for menurole in block
        ]
        if block_lines:
            embed.add_field(
                name='',
                value='\n'.join(block_lines)
            )
    return MessageArgs(embed=embed)


@register_template(
    id=3,
    name=_p(
        'template:shop|name', "Role Shop"
    ),
    description=_p(
        'template:shop|desc',
        "A single column display suitable for simple role shops"
    )
)
async def shop_template(menu) -> MessageArgs:
    menuroles = menu.roles
    width = max(len(str(menurole.config.price.data)) for menurole in menuroles)

    lines = []
    for menurole in menuroles:
        parts = []
        emoji = menurole.config.emoji
        role = menurole.config.role
        price = menurole.config.price
        duration = menurole.config.duration

        parts.append(f"`{price.value:>{width}} LC`")
        parts.append("|")

        if emoji.data:
            parts.append(emoji.formatted)

        parts.append(role.formatted)

        if duration.data:
            parts.append(f"({duration.formatted})")

        lines.append(' '.join(parts))

    description = '\n'.join(lines)

    embed = discord.Embed(
        title=menu.config.name.value,
        description=description,
        colour=discord.Colour.orange()
    )
    return MessageArgs(embed=embed)
