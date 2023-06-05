from enum import Enum
from . import babel

_p = babel._p


class LocaleMap(Enum):
    american_english = 'en-US'
    british_english = 'en-GB'
    bulgarian = 'bg'
    chinese = 'zh-CN'
    taiwan_chinese = 'zh-TW'
    croatian = 'hr'
    czech = 'cs'
    danish = 'da'
    dutch = 'nl'
    finnish = 'fi'
    french = 'fr'
    german = 'de'
    greek = 'el'
    hindi = 'hi'
    hungarian = 'hu'
    italian = 'it'
    japanese = 'ja'
    korean = 'ko'
    lithuanian = 'lt'
    norwegian = 'no'
    polish = 'pl'
    brazil_portuguese = 'pt-BR'
    romanian = 'ro'
    russian = 'ru'
    spain_spanish = 'es-ES'
    swedish = 'sv-SE'
    thai = 'th'
    turkish = 'tr'
    ukrainian = 'uk'
    vietnamese = 'vi'


locale_names = {
    'en-US': _p('localenames|locale:en-US', "American English"),
    'en-GB': _p('localenames|locale:en-GB', "British English"),
    'bg': _p('localenames|locale:bg', "Bulgarian"),
    'zh-CN': _p('localenames|locale:zh-CN', "Chinese"),
    'zh-TW': _p('localenames|locale:zh-TW', "Taiwan Chinese"),
    'hr': _p('localenames|locale:hr', "Croatian"),
    'cs': _p('localenames|locale:cs', "Czech"),
    'da': _p('localenames|locale:da', "Danish"),
    'nl': _p('localenames|locale:nl', "Dutch"),
    'fi': _p('localenames|locale:fi', "Finnish"),
    'fr': _p('localenames|locale:fr', "French"),
    'de': _p('localenames|locale:de', "German"),
    'el': _p('localenames|locale:el', "Greek"),
    'hi': _p('localenames|locale:hi', "Hindi"),
    'hu': _p('localenames|locale:hu', "Hungarian"),
    'it': _p('localenames|locale:it', "Italian"),
    'ja': _p('localenames|locale:ja', "Japanese"),
    'ko': _p('localenames|locale:ko', "Korean"),
    'lt': _p('localenames|locale:lt', "Lithuanian"),
    'no': _p('localenames|locale:no', "Norwegian"),
    'pl': _p('localenames|locale:pl', "Polish"),
    'pt-BR': _p('localenames|locale:pt-BR', "Brazil Portuguese"),
    'ro': _p('localenames|locale:ro', "Romanian"),
    'ru': _p('localenames|locale:ru', "Russian"),
    'es-ES': _p('localenames|locale:es-ES', "Spain Spanish"),
    'sv-SE': _p('localenames|locale:sv-SE', "Swedish"),
    'th': _p('localenames|locale:th', "Thai"),
    'tr': _p('localenames|locale:tr', "Turkish"),
    'uk': _p('localenames|locale:uk', "Ukrainian"),
    'vi': _p('localenames|locale:vi', "Vietnamese"),
}
