import logging

import psycopg2 as psy

from meta import log, conf
from constants import DATA_VERSION
from .cursor import DictLoggingCursor


# Set up database connection
log("Establishing connection.", "DB_INIT", level=logging.DEBUG)
conn = psy.connect(conf.bot['database'], cursor_factory=DictLoggingCursor)

# Replace char used by the connection for query formatting
_replace_char: str = '%s'

# conn.set_trace_callback(lambda message: log(message, context="DB_CONNECTOR", level=logging.DEBUG))
# sq.register_adapter(datetime, lambda dt: dt.timestamp())


# Check the version matches the required version
with conn:
    log("Checking db version.", "DB_INIT")
    cursor = conn.cursor()

    # Get last entry in version table, compare against desired version
    cursor.execute("SELECT * FROM VersionHistory ORDER BY time DESC LIMIT 1")
    current_version, _, _ = cursor.fetchone()

    if current_version != DATA_VERSION:
        # Complain
        raise Exception(
            ("Database version is {}, required version is {}. "
             "Please migrate database.").format(current_version, DATA_VERSION)
        )

    cursor.close()


log("Established connection.", "DB_INIT")
