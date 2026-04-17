import logging
from typing import Optional

import psycopg.errors
from psycopg import AsyncCursor, sql
from psycopg.abc import Query, Params
from psycopg._encodings import pgconn_encoding

logger = logging.getLogger(__name__)


class AsyncLoggingCursor(AsyncCursor):
    def mogrify_query(self, query: Query):
        if isinstance(query, str):
            msg = query
        elif isinstance(query, (sql.SQL, sql.Composed)):
            msg = query.as_string(self)
        elif isinstance(query, bytes):
            msg = query.decode(pgconn_encoding(self._conn.pgconn), 'replace')
        else:
            msg = repr(query)
        return msg

    async def execute(self, query: Query, params: Optional[Params] = None, **kwargs):
        if logging.DEBUG >= logger.getEffectiveLevel():
            msg = self.mogrify_query(query)
            logger.debug(
                "Executing query (%s) with values %s", msg, params,
                extra={'action': "Query Execute"}
            )
        try:
            return await super().execute(query, params=params, **kwargs)
        # --- AI-MODIFIED (2026-04-17) ---
        # Purpose: UniqueViolation is the expected outcome of the race
        # inside Row.fetch_or_create() -- two callers SELECT, both miss,
        # both INSERT, one wins. fetch_or_create() catches the loser and
        # re-fetches, so the program continues correctly. Logging this
        # at ERROR with stack_info pollutes the error webhook (Discord
        # ping spam) and the pm2 error log on every concurrent member
        # join. Demote to WARNING without a stack trace so the event
        # is still greppable but not paging anyone. We still re-raise so
        # callers that DON'T expect the violation surface it normally.
        except psycopg.errors.UniqueViolation:
            msg = self.mogrify_query(query)
            logger.warning(
                "UniqueViolation on insert (race-handled by caller). "
                "Query (%s) with parameters %s.",
                msg, params,
                extra={'action': "Query Execute"}
            )
            raise
        # --- END AI-MODIFIED ---
        except Exception:
            msg = self.mogrify_query(query)
            logger.exception(
                "Exception during query execution. Query (%s) with parameters %s.",
                msg, params,
                extra={'action': "Query Execute"},
                stack_info=True
            )
            # --- AI-MODIFIED (2026-04-02) ---
            # Purpose: Re-raise after logging so the real DB error propagates
            # instead of being swallowed and surfacing as a misleading
            # ProgrammingError('no result available') from fetchall()
            # --- Original code (commented out for rollback) ---
            # (no raise statement existed here -- exception was silently swallowed)
            # --- End original code ---
            raise
            # --- END AI-MODIFIED ---
