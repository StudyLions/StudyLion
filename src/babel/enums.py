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
    hebrew = 'he-IL'


# Original Discord names
locale_names = {
    'id': (_p('localenames|locale:id', "Indonesian"), "Bahasa Indonesia"),
    'da': (_p('localenames|locale:da', "Danish"), "Dansk"),
    'de': (_p('localenames|locale:de', "German"), "Deutsch"),
    'en-GB': (_p('localenames|locale:en-GB', "English, UK"), "English, UK"),
    'en-US': (_p('localenames|locale:en-US', "English, US"), "English, US"),
    'es-ES': (_p('localenames|locale:es-ES', "Spanish"), "Español"),
    'fr': (_p('localenames|locale:fr', "French"), "Français"),
    'hr': (_p('localenames|locale:hr', "Croatian"), "Hrvatski"),
    'it': (_p('localenames|locale:it', "Italian"), "Italiano"),
    'lt': (_p('localenames|locale:lt', "Lithuanian"), "Lietuviškai"),
    'hu': (_p('localenames|locale:hu', "Hungarian"), "Magyar"),
    'nl': (_p('localenames|locale:nl', "Dutch"), "Nederlands"),
    'no': (_p('localenames|locale:no', "Norwegian"), "Norsk"),
    'pl': (_p('localenames|locale:pl', "Polish"), "Polski"),
    'pt-BR': (_p('localenames|locale:pt-BR', "Portuguese, Brazilian"), "Português do Brasil"),
    'ro': (_p('localenames|locale:ro', "Romanian, Romania"), "Română"),
    'fi': (_p('localenames|locale:fi', "Finnish"), "Suomi"),
    'sv-SE': (_p('localenames|locale:sv-SE', "Swedish"), "Svenska"),
    'vi': (_p('localenames|locale:vi', "Vietnamese"), "Tiếng Việt"),
    'tr': (_p('localenames|locale:tr', "Turkish"), "Türkçe"),
    'cs': (_p('localenames|locale:cs', "Czech"), "Čeština"),
    'el': (_p('localenames|locale:el', "Greek"), "Ελληνικά"),
    'bg': (_p('localenames|locale:bg', "Bulgarian"), "български"),
    'ru': (_p('localenames|locale:ru', "Russian"), "Pусский"),
    'uk': (_p('localenames|locale:uk', "Ukrainian"), "Українська"),
    'hi': (_p('localenames|locale:hi', "Hindi"), "हिन्दी"),
    'th': (_p('localenames|locale:th', "Thai"), "ไทย"),
    'zh-CN': (_p('localenames|locale:zh-CN', "Chinese, China"), "中文"),
    'ja': (_p('localenames|locale:ja', "Japanese"), "日本語"),
    'zh-TW': (_p('localenames|locale:zh-TW', "Chinese, Taiwan"), "繁體中文"),
    'ko': (_p('localenames|locale:ko', "Korean"), "한국어"),
}

# More names for languages not supported by Discord
locale_names |= {
    'he': (_p('localenames|locale:he', "Hebrew"), "Hebrew"),
    'he-IL': (_p('localenames|locale:he-IL', "Hebrew"), "Hebrew"),
    'ceaser': (_p('localenames|locale:test', "Test Language"), "dfbtfs"),
}
