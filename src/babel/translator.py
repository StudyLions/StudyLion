from typing import Optional
import logging
from contextvars import ContextVar
from collections import defaultdict
from enum import Enum

import gettext
import string

from discord.app_commands import Translator, locale_str
from discord.enums import Locale

# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Import override cache for text branding feature
from .overrides import override_cache
# --- END AI-MODIFIED ---

logger = logging.getLogger(__name__)


SOURCE_LOCALE = 'en_GB'
ctx_locale: ContextVar[str] = ContextVar('locale', default=SOURCE_LOCALE)
ctx_translator: ContextVar['LeoBabel'] = ContextVar('translator', default=None)  # type: ignore
# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Guild context for text branding override lookup
ctx_guildid: ContextVar[Optional[int]] = ContextVar('guildid', default=None)
# --- END AI-MODIFIED ---

null = gettext.NullTranslations()

# --- AI-MODIFIED (2026-05-31) ---
# Purpose: Reusable formatter used to validate that a resolved translation is a
# parseable brace-format string before the caller runs .format() on it.
# See LeoBabel.t (ticket #0102 follow-up).
_brace_formatter = string.Formatter()
# --- END AI-MODIFIED ---


class LeoBabel(Translator):
    def __init__(self):
        self.supported_locales = {loc.name for loc in Locale}
        self.supported_domains = {}
        self.translators = defaultdict(dict)  # locale -> domain -> GNUTranslator

    def read_supported(self):
        """
        Load supported localisations and domains from the config.
        """
        from meta import conf

        locales = conf.babel.get('locales', '')
        stripped = (loc.strip(', ') for loc in locales.split(','))
        self.supported_locales = {loc for loc in stripped if loc}
        self.supported_locales.add(SOURCE_LOCALE)

        domains = conf.babel.get('domains', '')
        stripped = (dom.strip(', ') for dom in domains.split(','))
        self.supported_domains = {dom for dom in stripped if dom}

    async def load(self):
        self._load()

    def _load(self):
        """
        Initialise the gettext translators for the supported_locales.
        """
        self.read_supported()
        missing = []
        loaded = []
        for locale in self.supported_locales:
            for domain in self.supported_domains:
                if locale == SOURCE_LOCALE:
                    continue
                try:
                    translator = gettext.translation(domain, "locales/", languages=[locale])
                    loaded.append(f"Loaded translator for <locale: {locale}> <domain: {domain}>")
                except OSError:
                    # Presume translation does not exist
                    missing.append(f"Could not load translator for supported <locale: {locale}> <domain: {domain}>")
                    translator = null

                self.translators[locale][domain] = translator
        if missing:
            logger.warning('\n'.join(("Missing Translators:", *missing)))
        if loaded:
            logger.debug('\n'.join(("Loaded Translators:", *loaded)))

    async def unload(self):
        self.translators.clear()

    def get_translator(self, locale: Optional[str], domain):
        locale = locale or SOURCE_LOCALE
        locale = locale.replace('-', '_') if locale else None
        if locale == SOURCE_LOCALE:
            translator = null
        elif locale in self.supported_locales and domain in self.supported_domains:
            translator = self.translators[locale].get(domain, None)
            if translator is None:
                # This should never really happen because we already loaded the supported translators
                logger.warning(
                    f"Translator missing for supported <locale: {locale}> "
                    "and <domain: {domain}>. Setting NullTranslator."
                )
                translator = self.translators[locale][domain] = null
        else:
            # Unsupported
            translator = null
        return translator

    # --- AI-REPLACED (2026-04-01) ---
    # Reason: Add guild text override lookup for Text Branding premium feature
    # What the new code does better: Checks per-guild text overrides (from
    #   guild_text_overrides table) before falling back to locale translations.
    #   Only applies when the guild has active premium. Override key is the
    #   gettext context string (first arg to _p).
    # --- Original code (commented out for rollback) ---
    # def t(self, lazystr, locale=None):
    #     domain = lazystr.domain
    #     translator = self.get_translator(locale or lazystr.locale or ctx_locale.get(), domain)
    #     return lazystr._translate_with(translator)
    # --- End original code ---
    def t(self, lazystr, locale=None):
        guildid = ctx_guildid.get()
        if guildid and override_cache.is_premium(guildid):
            if lazystr.method == Method.PGETTEXT:
                text_key = lazystr.args[0]
                override = override_cache.get_override(guildid, text_key)
                if override is not None:
                    return override
            elif lazystr.method == Method.NPGETTEXT:
                text_key = lazystr.args[0]
                singular, plural = override_cache.get_plural_override(guildid, text_key)
                if singular is not None:
                    n = lazystr.args[3]
                    return singular if n == 1 else (plural or singular)

        domain = lazystr.domain
        translator = self.get_translator(locale or lazystr.locale or ctx_locale.get(), domain)
        # --- AI-MODIFIED (2026-05-31) ---
        # Purpose: Guard against malformed translations. A bad translation export
        # truncated placeholders mid-name across ~24 locales / 45 .mo files
        # (e.g. "...**`{ad..."), and each is a latent str.format() crash
        # ("expected '}' before end of string") for that locale. If the resolved
        # translation is not a valid brace-format string, fall back to the source
        # (English) message so the caller's .format(...) cannot crash the interaction.
        # Only parses strings containing '{' (skips plain text); the source is
        # computed only on the rare failure path. Ticket #0102 follow-up.
        # --- Original code (commented out for rollback) ---
        # return lazystr._translate_with(translator)
        # --- End original code ---
        translated = lazystr._translate_with(translator)
        if isinstance(translated, str) and '{' in translated:
            try:
                for _ in _brace_formatter.parse(translated):
                    pass
            except ValueError:
                logger.warning(
                    "Malformed translation fell back to source (domain=%s, locale=%s, context=%r): %r",
                    domain, (locale or lazystr.locale or ctx_locale.get()),
                    (lazystr.args[0] if lazystr.args else None), translated,
                )
                translated = lazystr.message
        return translated
        # --- END AI-MODIFIED ---
    # --- END AI-REPLACED ---

    # --- AI-MODIFIED (2026-05-05) ---
    # Purpose: Sanitize command/parameter name translations for Discord.
    # Discord's name_localizations pattern: ^[-_\p{L}\p{N}\p{sc=Deva}\p{sc=Thai}]{1,32}$
    # Unicode letters (accents, cedillas, CJK, etc.) ARE allowed.
    # Invalid name_localizations in ANY locale cause the ENTIRE sync
    # to fail (HTTP 400), blocking ALL slash commands from registering.
    # Fix: sanitize name translations (lowercase, spaces->underscores,
    # strip chars not matching Discord's allowed set: Unicode letters,
    # digits, hyphens, underscores).
    # --- Original code (commented out for rollback) ---
    # async def translate(self, string: locale_str, locale: Locale, context):
    #     loc = locale.value.replace('-', '_')
    #     if loc in self.supported_locales:
    #         domain = string.extras.get('domain', None)
    #         if domain is None and isinstance(string, LazyStr):
    #             logger.debug(...)
    #             return None
    #         translator = self.get_translator(loc, domain)
    #         if not isinstance(string, LazyStr):
    #             lazy = LazyStr(Method.GETTEXT, string.message)
    #         else:
    #             lazy = string
    #         return lazy._translate_with(translator)
    # --- End original code ---
    import re
    _cmd_name_strip_re = re.compile(r'[^\w-]', re.UNICODE)

    @staticmethod
    def _sanitize_cmd_name(name):
        """Sanitize a translated command/parameter name for Discord API."""
        s = name.lower().replace(' ', '_')
        s = LeoBabel._cmd_name_strip_re.sub('', s)
        s = s[:32].strip('-_')
        return s if s else None

    # --- AI-MODIFIED (2026-06-02) ---
    # Purpose: Guard command/group/parameter DESCRIPTIONS and CHOICE names the
    # same way names are guarded above. Discord requires these to be 1-100 chars
    # in length; an empty (or whitespace-only, or >100) translation in ANY locale
    # makes the ENTIRE global command-tree sync fail with HTTP 400 / code 50035,
    # so the whole tree (and any new command changes) never registers.
    # A corrupt translation export left the pomodoro 'channel_name' parameter
    # description empty in 6 locales (hr/id/fi/it/pl/es-ES), which was blocking
    # every shard-0 sync. Returning None omits that locale's localization so
    # Discord falls back to the (valid) source string; truncating to 100 keeps
    # legitimately-long translations valid.
    @staticmethod
    def _sanitize_cmd_description(desc):
        """Clamp a translated description/choice name to Discord's 1-100 char
        limit. Returns None (omit the localization -> fall back to the source
        string) when empty after stripping, so corrupt/empty translation data
        can't fail the whole command-tree sync."""
        if desc is None:
            return None
        d = desc.strip()
        if not d:
            return None
        return d[:100]
    # --- END AI-MODIFIED ---

    async def translate(self, string: locale_str, locale: Locale, context):
        loc = locale.value.replace('-', '_')
        if loc in self.supported_locales:
            domain = string.extras.get('domain', None)
            if domain is None and isinstance(string, LazyStr):
                logger.debug(
                    f"LeoBabel cannot translate a locale_str with no domain set. Context: {context}, String: {string}"
                )
                return None

            translator = self.get_translator(loc, domain)
            if not isinstance(string, LazyStr):
                lazy = LazyStr(Method.GETTEXT, string.message)
            else:
                lazy = string
            result = lazy._translate_with(translator)

            if result is not None and hasattr(context, 'location'):
                from discord.app_commands import TranslationContextLocation
                name_locations = (
                    TranslationContextLocation.command_name,
                    TranslationContextLocation.group_name,
                    TranslationContextLocation.parameter_name,
                )
                # --- AI-MODIFIED (2026-06-02) ---
                # Also clamp descriptions + choice names to Discord's 1-100 length
                # limit (empty/over-long translations otherwise fail the entire
                # command sync with code 50035). See _sanitize_cmd_description.
                desc_locations = (
                    TranslationContextLocation.command_description,
                    TranslationContextLocation.group_description,
                    TranslationContextLocation.parameter_description,
                    TranslationContextLocation.choice_name,
                )
                if context.location in name_locations:
                    result = self._sanitize_cmd_name(result)
                elif context.location in desc_locations:
                    result = self._sanitize_cmd_description(result)
                # --- END AI-MODIFIED ---

            return result
    # --- END AI-MODIFIED ---


class Method(Enum):
    GETTEXT = 'gettext'
    NGETTEXT = 'ngettext'
    PGETTEXT = 'pgettext'
    NPGETTEXT = 'npgettext'


class LocalBabel:
    def __init__(self, domain):
        self.domain = domain

    @property
    def methods(self):
        return (self._, self._n, self._p, self._np)

    def _(self, message):
        return LazyStr(Method.GETTEXT, message, domain=self.domain)

    def _n(self, singular, plural, n):
        return LazyStr(Method.NGETTEXT, singular, plural, n, domain=self.domain)

    def _p(self, context, message):
        return LazyStr(Method.PGETTEXT, context, message, domain=self.domain)

    def _np(self, context, singular, plural, n):
        return LazyStr(Method.NPGETTEXT, context, singular, plural, n, domain=self.domain)


class LazyStr(locale_str):
    __slots__ = ('method', 'args', 'domain', 'locale')

    def __init__(self, method, *args, locale=None, domain=None):
        self.method = method
        self.args = args
        self.domain = domain
        self.locale = locale

    @property
    def message(self):
        return self._translate_with(null)

    @property
    def extras(self):
        return {'locale': self.locale, 'domain': self.domain}

    def __str__(self):
        return self.message

    def _translate_with(self, translator: gettext.GNUTranslations):
        method = getattr(translator, self.method.value)
        return method(*self.args)

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.method}, {self.args!r}, locale={self.locale}, domain={self.domain})'

    def __eq__(self, obj: object) -> bool:
        return isinstance(obj, locale_str) and self.message == obj.message

    def __hash__(self) -> int:
        return hash(self.args)
