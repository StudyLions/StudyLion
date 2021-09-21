from __future__ import annotations

import logging
import traceback
import contextlib
from cachetools import LRUCache
from typing import Mapping
import psycopg2
import asyncio

from meta import log, client
from utils.lib import DotDict

from .connection import conn
from .queries import insert, insert_many, select_where, update_where, upsert, delete_where, update_many


# Global cache of interfaces
tables: Mapping[str, Table] = DotDict()


def _connection_guard(func):
    """
    Query decorator that performs a client shutdown when the database isn't responding.
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            log("Critical error performing database query. Shutting down. "
                "Exception traceback follows.\n{}".format(
                    traceback.format_exc()
                ),
                context="DATABASE_QUERY",
                level=logging.ERROR)
            asyncio.create_task(client.close())
            raise Exception("Critical error, database connection closed. Restarting client.")
    return wrapper


class Table:
    """
    Transparent interface to a single table structure in the database.
    Contains standard methods to access the table.
    Intended to be subclassed to provide more derivative access for specific tables.
    """
    conn = conn
    queries = DotDict()

    def __init__(self, name, attach_as=None):
        self.name = name
        tables[attach_as or name] = self

    @_connection_guard
    def select_where(self, *args, **kwargs):
        with self.conn:
            return select_where(self.name, *args, **kwargs)

    def select_one_where(self, *args, **kwargs):
        rows = self.select_where(*args, **kwargs)
        return rows[0] if rows else None

    @_connection_guard
    def update_where(self, *args, **kwargs):
        with self.conn:
            return update_where(self.name, *args, **kwargs)

    @_connection_guard
    def delete_where(self, *args, **kwargs):
        with self.conn:
            return delete_where(self.name, *args, **kwargs)

    @_connection_guard
    def insert(self, *args, **kwargs):
        with self.conn:
            return insert(self.name, *args, **kwargs)

    @_connection_guard
    def insert_many(self, *args, **kwargs):
        with self.conn:
            return insert_many(self.name, *args, **kwargs)

    @_connection_guard
    def update_many(self, *args, **kwargs):
        with self.conn:
            return update_many(self.name, *args, **kwargs)

    @_connection_guard
    def upsert(self, *args, **kwargs):
        with self.conn:
            return upsert(self.name, *args, **kwargs)

    def save_query(self, func):
        """
        Decorator to add a saved query to the table.
        """
        self.queries[func.__name__] = func


class Row:
    __slots__ = ('table', 'data', '_pending')

    conn = conn

    def __init__(self, table, data, *args, **kwargs):
        super().__setattr__('table', table)
        self.data = data
        self._pending = None

    @property
    def rowid(self):
        return self.table.id_from_row(self.data)

    def __repr__(self):
        return "Row[{}]({})".format(
            self.table.name,
            ', '.join("{}={!r}".format(field, getattr(self, field)) for field in self.table.columns)
        )

    def __getattr__(self, key):
        if key in self.table.columns:
            if self._pending and key in self._pending:
                return self._pending[key]
            else:
                return self.data[key]
        else:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        if key in self.table.columns:
            if self._pending is None:
                self.update(**{key: value})
            else:
                self._pending[key] = value
        else:
            super().__setattr__(key, value)

    @contextlib.contextmanager
    def batch_update(self):
        if self._pending:
            raise ValueError("Nested batch updates for {}!".format(self.__class__.__name__))

        self._pending = {}
        try:
            yield self._pending
        finally:
            if self._pending:
                self.update(**self._pending)
            self._pending = None

    def _refresh(self):
        row = self.table.select_one_where(self.table.dict_from_id(self.rowid))
        if not row:
            raise ValueError("Refreshing a {} which no longer exists!".format(type(self).__name__))
        self.data = row

    def update(self, **values):
        rows = self.table.update_where(values, **self.table.dict_from_id(self.rowid))
        self.data = rows[0]

    @classmethod
    def _select_where(cls, _extra=None, **conditions):
        return select_where(cls._table, **conditions)

    @classmethod
    def _insert(cls, **values):
        return insert(cls._table, **values)

    @classmethod
    def _update_where(cls, values, **conditions):
        return update_where(cls._table, values, **conditions)


class RowTable(Table):
    __slots__ = (
        'name',
        'columns',
        'id_col',
        'multi_key',
        'row_cache'
    )

    conn = conn

    def __init__(self, name, columns, id_col, use_cache=True, cache=None, cache_size=1000, **kwargs):
        super().__init__(name, **kwargs)
        self.name = name
        self.columns = columns
        self.id_col = id_col
        self.multi_key = isinstance(id_col, tuple)
        self.row_cache = (cache or LRUCache(cache_size)) if use_cache else None

    def id_from_row(self, row):
        if self.multi_key:
            return tuple(row[key] for key in self.id_col)
        else:
            return row[self.id_col]

    def dict_from_id(self, rowid):
        if self.multi_key:
            return dict(zip(self.id_col, rowid))
        else:
            return {self.id_col: rowid}

    # Extend original Table update methods to modify the cached rows
    def insert(self, *args, **kwargs):
        data = super().insert(*args, **kwargs)
        if self.row_cache is not None:
            self.row_cache[self.id_from_row(data)] = Row(self, data)
        return data

    def insert_many(self, *args, **kwargs):
        data = super().insert_many(*args, **kwargs)
        if self.row_cache is not None:
            for data_row in data:
                cached_row = self.row_cache.get(self.id_from_row(data_row), None)
                if cached_row is not None:
                    cached_row.data = data_row
        return data

    def update_where(self, *args, **kwargs):
        data = super().update_where(*args, **kwargs)
        if self.row_cache is not None:
            for data_row in data:
                cached_row = self.row_cache.get(self.id_from_row(data_row), None)
                if cached_row is not None:
                    cached_row.data = data_row
        return data

    def update_many(self, *args, **kwargs):
        data = super().update_many(*args, **kwargs)
        if self.row_cache is not None:
            for data_row in data:
                cached_row = self.row_cache.get(self.id_from_row(data_row), None)
                if cached_row is not None:
                    cached_row.data = data_row
        return data

    def delete_where(self, *args, **kwargs):
        data = super().delete_where(*args, **kwargs)
        if self.row_cache is not None:
            for data_row in data:
                self.row_cache.pop(self.id_from_row(data_row), None)
        return data

    def upsert(self, *args, **kwargs):
        data = super().upsert(*args, **kwargs)
        if self.row_cache is not None:
            rowid = self.id_from_row(data)
            cached_row = self.row_cache.get(rowid, None)
            if cached_row is not None:
                cached_row.data = data
            else:
                self.row_cache[rowid] = Row(self, data)
        return data

    # New methods to fetch and create rows
    def _make_rows(self, *data_rows):
        """
        Create or retrieve Row objects for each provided data row.
        If the rows already exist in cache, updates the cached row.
        """
        if self.row_cache is not None:
            rows = []
            for data_row in data_rows:
                rowid = self.id_from_row(data_row)

                cached_row = self.row_cache.get(rowid, None)
                if cached_row is not None:
                    cached_row.data = data_row
                    row = cached_row
                else:
                    row = Row(self, data_row)
                    self.row_cache[rowid] = row
                rows.append(row)
        else:
            rows = [Row(self, data_row) for data_row in data_rows]
        return rows

    def create_row(self, *args, **kwargs):
        data = self.insert(*args, **kwargs)
        return self._make_rows(data)[0]

    def fetch_rows_where(self, *args, **kwargs):
        # TODO: Handle list of rowids here?
        data = self.select_where(*args, **kwargs)
        return self._make_rows(*data)

    def fetch(self, rowid):
        """
        Fetch the row with the given id, retrieving from cache where possible.
        """
        row = self.row_cache.get(rowid, None) if self.row_cache is not None else None
        if row is None:
            rows = self.fetch_rows_where(**self.dict_from_id(rowid))
            row = rows[0] if rows else None
        return row

    def fetch_or_create(self, rowid=None, **kwargs):
        """
        Helper method to fetch a row with the given id or fields, or create it if it doesn't exist.
        """
        if rowid is not None:
            row = self.fetch(rowid)
        else:
            data = self.select_where(**kwargs)
            row = self._make_rows(data[0])[0] if data else None

        if row is None:
            creation_kwargs = kwargs
            if rowid is not None:
                creation_kwargs.update(self.dict_from_id(rowid))
            row = self.create_row(**creation_kwargs)
        return row
