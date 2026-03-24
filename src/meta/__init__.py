from .LionBot import LionBot
from .LionCog import LionCog
from .LionContext import LionContext
from .LionTree import LionTree

from .logger import logging_context, log_wrap, log_action_stack, log_context, log_app
from .config import conf, configEmoji
from .args import args

# --- AI-MODIFIED (2026-03-17) ---
# Purpose: Central website URL constant driven by config file.
# Test bot reads staging URL, live bot reads lionbot.org.
WEBSITE_URL = conf.get('website_url', 'https://lionbot.org').rstrip('/')
# --- END AI-MODIFIED ---
from .app import appname, shard_talk, appname_from_shard, shard_from_appname
from .errors import HandledException, UserInputError, ResponseTimedOut, SafeCancellation, UserCancelled
from .context import context, ctx_bot

from . import sharding
from . import logger
from . import app
