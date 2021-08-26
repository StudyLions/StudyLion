import logging
import contextlib
from itertools import chain
from enum import Enum

import psycopg2 as psy
from cachetools import LRUCache

from utils.lib import DotDict
from meta import log, conf
from constants import DATA_VERSION
from .custom_cursor import DictLoggingCursor


# Set up database connection
log("Establishing connection.", "DB_INIT", level=logging.DEBUG)
conn = psy.connect(conf.bot['database'], cursor_factory=DictLoggingCursor)

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


# --------------- Data Interface Classes ---------------
class Table:
    """
    Transparent interface to a single table structure in the database.
    Contains standard methods to access the table.
    Intended to be subclassed to provide more derivative access for specific tables.
    """
    conn = conn
    queries = DotDict()

    def __init__(self, name):
        self.name = name

    def select_where(self, *args, **kwargs):
        with self.conn:
            return select_where(self.name, *args, **kwargs)

    def select_one_where(self, *args, **kwargs):
        with self.conn:
            rows = self.select_where(*args, **kwargs)
            return rows[0] if rows else None

    def update_where(self, *args, **kwargs):
        with self.conn:
            return update_where(self.name, *args, **kwargs)

    def delete_where(self, *args, **kwargs):
        with self.conn:
            return delete_where(self.name, *args, **kwargs)

    def insert(self, *args, **kwargs):
        with self.conn:
            return insert(self.name, *args, **kwargs)

    def insert_many(self, *args, **kwargs):
        with self.conn:
            return insert_many(self.name, *args, **kwargs)

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
        return self.data[self.table.id_col]

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
            self.update(**self._pending)
            self._pending = None

    def _refresh(self):
        row = self.table.select_one_where(**{self.table.id_col: self.rowid})
        if not row:
            raise ValueError("Refreshing a {} which no longer exists!".format(type(self).__name__))
        self.data = row

    def update(self, **values):
        rows = self.table.update_where(values, **{self.table.id_col: self.rowid})
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
        'row_cache'
    )

    conn = conn

    def __init__(self, name, columns, id_col, use_cache=True, cache=None, cache_size=1000):
        self.name = name
        self.columns = columns
        self.id_col = id_col
        self.row_cache = (cache or LRUCache(cache_size)) if use_cache else None

    # Extend original Table update methods to modify the cached rows
    def update_where(self, *args, **kwargs):
        data = super().update_where(*args, **kwargs)
        if self.row_cache is not None:
            for data_row in data:
                cached_row = self.row_cache.get(data_row[self.id_col], None)
                if cached_row is not None:
                    cached_row.data = data_row
        return data

    def delete_where(self, *args, **kwargs):
        data = super().delete_where(*args, **kwargs)
        if self.row_cache is not None:
            for data_row in data:
                self.row_cache.pop(data_row[self.id_col], None)
        return data

    def upsert(self, *args, **kwargs):
        data = super().upsert(*args, **kwargs)
        if self.row_cache is not None:
            cached_row = self.row_cache.get(data[self.id_col], None)
            if cached_row is not None:
                cached_row.data = data
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
                rowid = data_row[self.id_col]

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
            rows = self.fetch_rows_where(**{self.id_col: rowid})
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
                creation_kwargs[self.id_col] = rowid
            row = self.create_row(**creation_kwargs)
        return row


# --------------- Query Builders ---------------
def select_where(table, select_columns=None, cursor=None, _extra='', **conditions):
    """
    Select rows from the given table matching the conditions
    """
    criteria, criteria_values = _format_conditions(conditions)
    col_str = _format_selectkeys(select_columns)

    if conditions:
        where_str = "WHERE {}".format(criteria)
    else:
        where_str = ""

    cursor = cursor or conn.cursor()
    cursor.execute(
        'SELECT {} FROM {} {} {}'.format(col_str, table, where_str, _extra),
        criteria_values
    )
    return cursor.fetchall()


def update_where(table, valuedict, cursor=None, **conditions):
    """
    Update rows in the given table matching the conditions
    """
    key_str, key_values = _format_updatestr(valuedict)
    criteria, criteria_values = _format_conditions(conditions)

    if conditions:
        where_str = "WHERE {}".format(criteria)
    else:
        where_str = ""

    cursor = cursor or conn.cursor()
    cursor.execute(
        'UPDATE {} SET {} {} RETURNING *'.format(table, key_str, where_str),
        tuple((*key_values, *criteria_values))
    )
    return cursor.fetchall()


def delete_where(table, cursor=None, **conditions):
    """
    Delete rows in the given table matching the conditions
    """
    criteria, criteria_values = _format_conditions(conditions)

    cursor = cursor or conn.cursor()
    cursor.execute(
        'DELETE FROM {} WHERE {}'.format(table, criteria),
        criteria_values
    )
    return cursor.fetchall()


def insert(table, cursor=None, allow_replace=False, **values):
    """
    Insert the given values into the table
    """
    keys, values = zip(*values.items())

    key_str = _format_insertkeys(keys)
    value_str, values = _format_insertvalues(values)

    action = 'REPLACE' if allow_replace else 'INSERT'

    cursor = cursor or conn.cursor()
    cursor.execute(
        '{} INTO {} {} VALUES {} RETURNING *'.format(action, table, key_str, value_str),
        values
    )
    return cursor.fetchone()


def insert_many(table, *value_tuples, insert_keys=None, cursor=None):
    """
    Insert all the given values into the table
    """
    key_str = _format_insertkeys(insert_keys)
    value_strs, value_tuples = zip(*(_format_insertvalues(value_tuple) for value_tuple in value_tuples))

    value_str = ", ".join(value_strs)
    values = tuple(chain(*value_tuples))

    cursor = cursor or conn.cursor()
    cursor.execute(
        'INSERT INTO {} {} VALUES {} RETURNING *'.format(table, key_str, value_str),
        values
    )
    return cursor.fetchall()


def upsert(table, constraint, cursor=None, **values):
    """
    Insert or on conflict update.
    """
    valuedict = values
    keys, values = zip(*values.items())

    key_str = _format_insertkeys(keys)
    value_str, values = _format_insertvalues(values)
    update_key_str, update_key_values = _format_updatestr(valuedict)

    if not isinstance(constraint, str):
        constraint = ", ".join(constraint)

    cursor = cursor or conn.cursor()
    cursor.execute(
        'INSERT INTO {} {} VALUES {} ON CONFLICT({}) DO UPDATE SET {} RETURNING *'.format(
            table, key_str, value_str, constraint, update_key_str
        ),
        tuple((*values, *update_key_values))
    )
    return cursor.fetchone()


# --------------- Query Formatting Tools ---------------
# Replace char used by the connection for query formatting
_replace_char: str = '%s'


class fieldConstants(Enum):
    """
    A collection of database field constants to use for selection conditions.
    """
    NULL = "IS NULL"
    NOTNULL = "IS NOT NULL"


class _updateField:
    __slots__ = ()
    _EMPTY = object()  # Return value for `value` indicating no value should be added

    def key_field(self, key):
        raise NotImplementedError

    def value_field(self, key):
        raise NotImplementedError


class UpdateValue(_updateField):
    __slots__ = ('key_str', 'value')

    def __init__(self, key_str, value=_updateField._EMPTY):
        self.key_str = key_str
        self.value = value

    def key_field(self, key):
        return self.key_str.format(key=key, value=_replace_char, replace=_replace_char)

    def value_field(self, key):
        return self.value


class UpdateValueAdd(_updateField):
    __slots__ = ('value',)

    def __init__(self, value):
        self.value = value

    def key_field(self, key):
        return "{key} = {key} + {replace}".format(key=key, replace=_replace_char)

    def value_field(self, key):
        return self.value


def _format_conditions(conditions):
    """
    Formats a dictionary of conditions into a string suitable for 'WHERE' clauses.
    Supports `IN` type conditionals.
    """
    if not conditions:
        return ("", tuple())

    values = []
    conditional_strings = []
    for key, item in conditions.items():
        if isinstance(item, (list, tuple)):
            conditional_strings.append("{} IN ({})".format(key, ", ".join([_replace_char] * len(item))))
            values.extend(item)
        elif isinstance(item, fieldConstants):
            conditional_strings.append("{} {}".format(key, item.value))
        else:
            conditional_strings.append("{}={}".format(key, _replace_char))
            values.append(item)

    return (' AND '.join(conditional_strings), values)


def _format_selectkeys(keys):
    """
    Formats a list of keys into a string suitable for `SELECT`.
    """
    if not keys:
        return "*"
    else:
        return ", ".join(keys)


def _format_insertkeys(keys):
    """
    Formats a list of keys into a string suitable for `INSERT`
    """
    if not keys:
        return ""
    else:
        return "({})".format(", ".join(keys))


def _format_insertvalues(values):
    """
    Formats a list of values into a string suitable for `INSERT`
    """
    value_str = "({})".format(", ".join(_replace_char for value in values))
    return (value_str, values)


def _format_updatestr(valuedict):
    """
    Formats a dictionary of keys and values into a string suitable for 'SET' clauses.
    """
    if not valuedict:
        return ("", tuple())

    key_fields = []
    values = []
    for key, value in valuedict.items():
        if isinstance(value, _updateField):
            key_fields.append(value.key_field(key))
            v = value.value_field(key)
            if v is not _updateField._EMPTY:
                values.append(value.value_field(key))
        else:
            key_fields.append("{} = {}".format(key, _replace_char))
            values.append(value)

    return (', '.join(key_fields), values)
