import discord
from discord import app_commands as appcmds
from discord.app_commands import Transformer
from discord.enums import AppCommandOptionType

from meta.errors import UserInputError

from babel.translator import ctx_translator

from .lib import parse_duration, strfdur
from . import util_babel


_, _p = util_babel._, util_babel._p


class DurationTransformer(Transformer):
    """
    Duration parameter, with included autocompletion.
    """

    def __init__(self, multiplier=1):
        # Multiplier used for a raw integer value
        self.multiplier = multiplier

    @property
    def type(self):
        return AppCommandOptionType.string

    async def transform(self, interaction: discord.Interaction, value: str) -> int:
        """
        Returns the number of seconds in the parsed duration.
        Raises UserInputError if the duration cannot be parsed.
        """
        translator = ctx_translator.get()
        t = translator.t

        if value.isdigit():
            return int(value) * self.multiplier
        duration = parse_duration(value)
        if duration is None:
            raise UserInputError(
                t(_p(
                    'utils:parse_dur|error',
                    "Cannot parse `{value}` as a duration."
                )).format(
                    value=value
                )
            )
        return duration or 0

    async def autocomplete(self, interaction: discord.Interaction, partial: str):
        """
        Default autocomplete for Duration parameters.

        Attempts to parse the partial value as a duration, and reformat it as an autocomplete choice.
        If not possible, displays an error message.
        """
        translator = ctx_translator.get()
        t = translator.t

        if partial.isdigit():
            duration = int(partial) * self.multiplier
        else:
            duration = parse_duration(partial)

        if duration is None:
            choice = appcmds.Choice(
                name=t(_p(
                    'util:Duration|acmpl|error',
                    "Cannot extract duration from \"{partial}\""
                )).format(partial=partial)[:100],
                value=partial
            )
        else:
            choice = appcmds.Choice(
                name=strfdur(duration, short=False, show_days=True)[:100],
                value=partial
            )
        return [choice]
