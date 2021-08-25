import logging
import meta

meta.logger.setLevel(logging.DEBUG)
logging.getLogger("discord").setLevel(logging.INFO)

import main  # noqa
