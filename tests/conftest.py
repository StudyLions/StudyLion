# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-20
# Purpose: pytest fixtures and configuration for StudyLion
#          unit and integration tests.
#          Provides lightweight stubs for discord.py and other
#          heavy dependencies so pure-logic tests can import
#          bot modules without the full runtime environment.
# ============================================================
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock
from enum import Enum

src_dir = Path(__file__).resolve().parent.parent / "src"

# ---- Stub out heavy external deps BEFORE any bot module imports ----
# discord.py and its sub-modules
_discord = MagicMock()
_discord.__name__ = "discord"
_discord.__path__ = []
_discord.__file__ = "<stub:discord>"
_discord.__spec__ = None
_discord.HTTPException = Exception
_discord.Forbidden = Exception
_discord.NotFound = Exception

# Stub enums that bot code imports by name
_StubLocale = type("Locale", (), {})
_StubChannelType = type("ChannelType", (), {"private": "private", "text": "text", "voice": "voice"})
_StubInteractionType = type("InteractionType", (), {"autocomplete": 4, "application_command": 2})
_StubTextStyle = type("TextStyle", (), {"short": 1, "paragraph": 2, "long": 2})

_discord_submodules = {
    "discord.ext": {},
    "discord.ext.commands": {
        "Bot": MagicMock, "Cog": type("Cog", (), {"listener": staticmethod(lambda *a, **kw: lambda f: f)}),
        "Context": MagicMock, "HybridCommand": MagicMock, "HybridCommandError": Exception,
        "hybrid_command": lambda *a, **kw: lambda f: f,
        "hybrid_group": lambda *a, **kw: lambda f: f,
        "command": lambda *a, **kw: lambda f: f,
        "group": lambda *a, **kw: lambda f: f,
        "CheckFailure": Exception,
    },
    "discord.ext.commands.errors": {
        "CommandInvokeError": Exception, "CheckFailure": Exception,
    },
    "discord.ext.tasks": {"loop": lambda *a, **kw: lambda f: f},
    "discord.app_commands": {
        "Translator": type("Translator", (), {}),
        "locale_str": type("locale_str", (str,), {
            "__new__": lambda cls, *args, **kw: str.__new__(cls, args[0] if args else ""),
            "__init__": lambda self, *args, **kw: None,
        }),
        "command": lambda *a, **kw: lambda f: f,
        "context_menu": lambda *a, **kw: lambda f: f,
        "guild_only": lambda f: f,
        "CommandTree": MagicMock,
        "Range": MagicMock(),
        "TranslationContextLocation": MagicMock(),
    },
    "discord.app_commands.transformers": {"AppCommandOptionType": MagicMock()},
    "discord.app_commands.namespace": {"Namespace": MagicMock},
    "discord.app_commands.errors": {"AppCommandError": Exception, "CommandInvokeError": Exception, "TransformerError": Exception},
    "discord.ui": {"View": MagicMock, "Modal": MagicMock, "Select": MagicMock, "Button": MagicMock, "button": MagicMock(), "TextInput": MagicMock},
    "discord.ui.button": {"Button": MagicMock, "ButtonStyle": MagicMock()},
    "discord.partial_emoji": {"_EmojiTag": type("_EmojiTag", (), {})},
    "discord.enums": {"Locale": _StubLocale, "ChannelType": _StubChannelType, "InteractionType": _StubInteractionType, "TextStyle": _StubTextStyle},
    "discord.types": {},
    "discord.types.interactions": {},
    "discord.utils": {"MISSING": object()},
    "discord.abc": {"Messageable": type("Messageable", (), {})},
}

# Wire all discord.X submodules as attributes on the discord package
for _sub_name in list(sys.modules.keys()):
    if _sub_name.startswith("discord."):
        _parts = _sub_name[len("discord."):].split(".")
        if len(_parts) == 1:
            setattr(_discord, _parts[0], sys.modules[_sub_name])

for submod_name, attrs in _discord_submodules.items():
    mod = types.ModuleType(submod_name)
    if "." in submod_name:
        mod.__path__ = []
    for attr_name, attr_val in attrs.items():
        setattr(mod, attr_name, attr_val)
    sys.modules[submod_name] = mod

sys.modules["discord"] = _discord

# aiohttp stub
_aiohttp = types.ModuleType("aiohttp")
_aiohttp.web = MagicMock()
_aiohttp.ClientSession = MagicMock
sys.modules["aiohttp"] = _aiohttp

# psycopg stubs -- use MagicMock so any attribute access works
for name in ["psycopg", "psycopg.sql", "psycopg.pq", "psycopg.rows",
             "psycopg.abc", "psycopg_pool"]:
    mod = MagicMock()
    mod.__name__ = name
    mod.__path__ = []
    mod.__file__ = f"<stub:{name}>"
    mod.__spec__ = None
    sys.modules[name] = mod

# Other light stubs
for name in ["topggpy", "cachetools", "iso8601", "bidict", "frozendict", "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont", "psutil"]:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        if name == "cachetools":
            mod.LRUCache = dict
            mod.TTLCache = dict
        if name == "iso8601":
            mod.parse_date = MagicMock()
        sys.modules[name] = mod

# Catch-all import hook: auto-stub any missing submodule of packages we've
# already stubbed, so we don't have to enumerate every internal subpackage.
_STUBBED_PREFIXES = ("discord.", "psycopg.", "psycopg_pool.", "aiohttp.", "topggpy.",
                     "PIL.", "bidict.", "frozendict.")


class _StubFinder:
    """Fallback finder that creates MagicMock modules for known stub prefixes."""
    def find_module(self, fullname, path=None):
        if any(fullname.startswith(p) or fullname == p.rstrip('.') for p in _STUBBED_PREFIXES):
            if fullname not in sys.modules:
                return self
        return None

    def load_module(self, fullname):
        if fullname in sys.modules:
            return sys.modules[fullname]
        mod = MagicMock()
        mod.__name__ = fullname
        mod.__path__ = []
        mod.__file__ = f"<stub:{fullname}>"
        mod.__loader__ = self
        mod.__spec__ = None
        sys.modules[fullname] = mod
        return mod


sys.meta_path.insert(0, _StubFinder())

# Now insert the src path
sys.path.insert(0, str(src_dir))

# Pre-populate the entire `meta` package and its key submodules with stubs.
# This avoids the deep import chain: meta -> LionBot -> data -> psycopg -> ...
# which requires the full bot runtime (config file, argparse, database).
import argparse as _argparse

_fake_args = _argparse.Namespace(config="config/bot.conf", shard=0, host="127.0.0.1", port="5001")

_meta_stubs = {
    "meta.args": {"args": _fake_args, "parser": _argparse.ArgumentParser()},
    "meta.config": {"Conf": MagicMock, "conf": MagicMock(), "shard_number": 0},
    "meta.context": {"context": MagicMock()},
    "meta.errors": {
        "SafeCancellation": type("SafeCancellation", (Exception,), {}),
        "HandledException": type("HandledException", (Exception,), {}),
        "UserInputError": type("UserInputError", (Exception,), {}),
        "UserCancelled": type("UserCancelled", (Exception,), {}),
        "ResponseTimedOut": type("ResponseTimedOut", (Exception,), {}),
    },
    "meta.logger": {
        "logging_context": MagicMock(),
        "log_context": MagicMock(),
        "log_action_stack": MagicMock(),
        "log_wrap": lambda *a, **kw: (lambda f: f),
        "set_logging_context": lambda **kw: None,
    },
    "meta.monitor": {
        "SystemMonitor": MagicMock,
        "ComponentMonitor": MagicMock,
        "StatusLevel": MagicMock(),
        "ComponentStatus": MagicMock,
    },
    "meta.LionContext": {"LionContext": MagicMock, "FlatContext": MagicMock},
    "meta.LionTree": {"LionTree": MagicMock},
    "meta.LionCog": {"LionCog": type("LionCog", (), {
        "placeholder_group": staticmethod(lambda *a, **kw: lambda f: f),
        "crossload_group": lambda self, *a: None,
        "depends": set(),
    })},
    "meta.LionBot": {"LionBot": MagicMock},
}

_meta_pkg = types.ModuleType("meta")
_meta_pkg.__path__ = [str(src_dir / "meta")]
_meta_pkg.__file__ = str(src_dir / "meta" / "__init__.py")

for _sub, _attrs in _meta_stubs.items():
    _mod = types.ModuleType(_sub)
    for _a, _v in _attrs.items():
        setattr(_mod, _a, _v)
    sys.modules[_sub] = _mod
    _leaf = _sub.split(".")[-1]
    setattr(_meta_pkg, _leaf, _mod)

# Also set top-level convenience attributes that meta/__init__.py normally exports
_meta_pkg.LionBot = _meta_stubs["meta.LionBot"]["LionBot"]
_meta_pkg.LionCog = _meta_stubs["meta.LionCog"]["LionCog"]
_meta_pkg.LionContext = _meta_stubs["meta.LionContext"]["LionContext"]
_meta_pkg.conf = _meta_stubs["meta.config"]["conf"]
_meta_pkg.WEBSITE_URL = "https://lionbot-website.vercel.app"
sys.modules["meta"] = _meta_pkg

# Stub wards module (imported by many cogs)
_wards = types.ModuleType("wards")
for _w in ["sys_admin_ward", "low_management_ward", "moderator_ward",
           "high_management_ward", "high_management_iward", "low_management"]:
    setattr(_wards, _w, MagicMock())
sys.modules["wards"] = _wards

# Stub data package
_data_pkg = types.ModuleType("data")
_data_pkg.__path__ = [str(src_dir / "data")]
_data_pkg.Registry = type("Registry", (), {"__init_subclass__": classmethod(lambda cls, **kw: None)})
_data_pkg.RowModel = MagicMock
_data_pkg.RowTable = MagicMock
_data_pkg.WeakCache = MagicMock
_data_pkg.Database = MagicMock
_data_pkg.RegisterEnum = lambda *a, **kw: None
_data_pkg.JOINTYPE = MagicMock()
_data_pkg.RawExpr = MagicMock
_data_pkg.ORDER = MagicMock()
_data_pkg.Table = MagicMock
sys.modules["data"] = _data_pkg
for _dsub in ["data.connector", "data.database", "data.models", "data.queries",
              "data.registry", "data.cursor", "data.columns"]:
    _dm = MagicMock()
    _dm.__name__ = _dsub
    _dm.__path__ = []
    sys.modules[_dsub] = _dm

# Stub core package
from enum import Enum as _Enum
class _RankType(_Enum):
    XP = 'XP',
    VOICE = 'VOICE',
    MESSAGE = 'MESSAGE',

_core_pkg = types.ModuleType("core")
_core_pkg.__path__ = [str(src_dir / "core")]
sys.modules["core"] = _core_pkg

_core_data = types.ModuleType("core.data")
_core_data.RankType = _RankType
_core_data.CoreData = MagicMock
sys.modules["core.data"] = _core_data

# Stub gui.errors
_gui_errors = types.ModuleType("gui.errors")
_gui_errors.RenderingException = type("RenderingException", (Exception,), {})
_gui = types.ModuleType("gui")
_gui.__path__ = [str(src_dir / "gui")]
_gui.errors = _gui_errors
sys.modules["gui"] = _gui
sys.modules["gui.errors"] = _gui_errors

# Stub utils.data
_utils_data = types.ModuleType("utils.data")
_utils_data.TemporaryTable = MagicMock
_utils_data.SAFECOINS = MagicMock
sys.modules["utils.data"] = _utils_data
