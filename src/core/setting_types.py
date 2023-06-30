"""
Additional abstract setting types useful for StudyLion settings.
"""
from settings.setting_types import IntegerSetting
from meta import conf
from meta.errors import UserInputError
from constants import MAX_COINS
from babel.translator import ctx_translator

from . import babel

_p = babel._p


class CoinSetting(IntegerSetting):
    """
    Setting type mixin describing a LionCoin setting.
    """
    _min = 0
    _max = MAX_COINS

    _accepts = _p('settype:coin|accepts', "A positive integral number of coins.")

    @classmethod
    async def _parse_string(cls, parent_id, string: str, **kwargs):
        """
        Parse the user input into an integer.
        """
        if not string:
            return None
        try:
            num = int(string)
        except Exception:
            t = ctx_translator.get().t

            raise UserInputError(t(_p(
                'settype:coin|parse|error:notinteger',
                "The coin quantity must be a positive integer!"
            ))) from None

        if num > cls._max:
            t = ctx_translator.get().t
            raise UserInputError(t(_p(
                'settype:coin|parse|error:too_large',
                "Provided number of coins was too high!"
            ))) from None
        elif num < cls._min:
            t = ctx_translator.get().t
            raise UserInputError(t(_p(
                'settype:coin|parse|error:too_large',
                "Provided number of coins was too low!"
            ))) from None

        return num

    @classmethod
    def _format_data(cls, parent_id, data, **kwargs):
        if data is not None:
            t = ctx_translator.get().t
            formatted = t(_p(
                'settype:coin|formatted',
                "{coin}**{amount}**"
            )).format(coin=conf.emojis.coin, amount=data)
            return formatted
