import logging
from psycopg2.extras import DictCursor, _ext

from meta import log


class DictLoggingCursor(DictCursor):
    def log(self):
        msg = self.query
        if isinstance(msg, bytes):
            msg = msg.decode(_ext.encodings[self.connection.encoding], 'replace')

        log(
            msg,
            context="DATABASE_QUERY",
            level=logging.DEBUG,
            post=False
        )

    def execute(self, query, vars=None):
        try:
            return super().execute(query, vars)
        finally:
            self.log()

    def callproc(self, procname, vars=None):
        try:
            return super().callproc(procname, vars)
        finally:
            self.log()
