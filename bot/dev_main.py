import logging
import meta

meta.logger.setLevel(logging.DEBUG)
logging.getLogger("discord").setLevel(logging.INFO)

from utils import interactive  # noqa

import main  # noqa
