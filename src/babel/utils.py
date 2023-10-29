from .translator import ctx_translator
from . import babel

_, _p, _np = babel._, babel._p, babel._np


MONTHS = _p(
    'utils|months',
    "January,February,March,April,May,June,July,August,September,October,November,December"
)

SHORT_MONTHS = _p(
    'utils|short_months',
    "Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec"
)


def local_month(month, short=False):
    string = MONTHS if not short else SHORT_MONTHS
    return ctx_translator.get().t(string).split(',')[month-1]
