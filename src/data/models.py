from typing import TypeVar, Type, Optional, Generic, Union
# from typing_extensions import Self
from weakref import WeakValueDictionary
from collections.abc import MutableMapping

from psycopg.rows import DictRow

from .table import Table
from .columns import Column
from . import queries as q
from .connector import Connector
from .registry import Registry


RowT = TypeVar('RowT', bound='RowModel')


class MISSING:
    __slots__ = ('oid',)

    def __init__(self, oid):
        self.oid = oid


class RowTable(Table, Generic[RowT]):
    __slots__ = (
        'model',
    )

    def __init__(self, name, model: Type[RowT], **kwargs):
        super().__init__(name, **kwargs)
        self.model = model

    @property
    def columns(self):
        return self.model._columns_

    @property
    def id_col(self):
        return self.model._key_

    @property
    def row_cache(self):
        return self.model._cache_

    def _many_query_adapter(self, *data):
        self.model._make_rows(*data)
        return data

    def _single_query_adapter(self, *data):
        if data:
            self.model._make_rows(*data)
            return data[0]
        else:
            return None

    def _delete_query_adapter(self, *data):
        self.model._delete_rows(*data)
        return data

    # New methods to fetch and create rows
    async def create_row(self, *args, **kwargs) -> RowT:
        data = await super().insert(*args, **kwargs)
        return self.model._make_rows(data)[0]

    def fetch_rows_where(self, *args, **kwargs) -> q.Select[list[RowT]]:
        # TODO: Handle list of rowids here?
        return q.Select(
            self.identifier,
            row_adapter=self.model._make_rows,
            connector=self.connector
        ).where(*args, **kwargs)


WK = TypeVar('WK')
WV = TypeVar('WV')


class WeakCache(Generic[WK, WV], MutableMapping[WK, WV]):
    def __init__(self, ref_cache):
        self.ref_cache = ref_cache
        self.weak_cache = WeakValueDictionary()

    def __getitem__(self, key):
        value = self.weak_cache[key]
        self.ref_cache[key] = value
        return value

    def __setitem__(self, key, value):
        self.weak_cache[key] = value
        self.ref_cache[key] = value

    def __delitem__(self, key):
        del self.weak_cache[key]
        try:
            del self.ref_cache[key]
        except KeyError:
            pass

    def __contains__(self, key):
        return key in self.weak_cache

    def __iter__(self):
        return iter(self.weak_cache)

    def __len__(self):
        return len(self.weak_cache)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key, default=None):
        if key in self:
            value = self[key]
            del self[key]
        else:
            value = default
        return value


# TODO: Implement getitem and setitem, for dynamic column access
class RowModel:
    __slots__ = ('data',)

    _schema_: str = 'public'
    _tablename_: Optional[str] = None
    _columns_: dict[str, Column] = {}

    # Cache to keep track of registered Rows
    _cache_: Union[dict, WeakValueDictionary, WeakCache] = None  # type: ignore

    _key_: tuple[str, ...] = ()
    _connector: Optional[Connector] = None
    _registry: Optional[Registry] = None

    # TODO: Proper typing for a classvariable which gets dynamically assigned in subclass
    table: RowTable = None

    def __init_subclass__(cls: Type[RowT], table: Optional[str] = None):
        """
        Set table, _columns_, and _key_.
        """
        if table is not None:
            cls._tablename_ = table

        if cls._tablename_ is not None:
            columns = {}
            for key, value in cls.__dict__.items():
                if isinstance(value, Column):
                    columns[key] = value

            cls._columns_ = columns
            if not cls._key_:
                cls._key_ = tuple(column.name for column in columns.values() if column.primary)
            cls.table = RowTable(cls._tablename_, cls, schema=cls._schema_)
            if cls._cache_ is None:
                cls._cache_ = WeakValueDictionary()

    def __new__(cls, data):
        # Registry pattern.
        # Ensure each rowid always refers to a single Model instance
        if data is not None:
            rowid = cls._id_from_data(data)

            cache = cls._cache_

            if (row := cache.get(rowid, None)) is not None:
                obj = row
            else:
                obj = cache[rowid] = super().__new__(cls)
        else:
            obj = super().__new__(cls)

        return obj

    @classmethod
    def as_tuple(cls):
        return (cls.table.identifier, ())

    def __init__(self, data):
        self.data = data

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    @classmethod
    def bind(cls, connector: Connector):
        if cls.table is None:
            raise ValueError("Cannot bind abstract RowModel")
        cls._connector = connector
        cls.table.bind(connector)
        return cls

    @classmethod
    def attach_to(cls, registry: Registry):
        cls._registry = registry
        return cls

    @property
    def _dict_(self):
        return {key: self.data[key] for key in self._key_}

    @property
    def _rowid_(self):
        return tuple(self.data[key] for key in self._key_)

    def __repr__(self):
        return "{}.{}({})".format(
            self.table.schema,
            self.table.name,
            ', '.join(repr(column.__get__(self)) for column in self._columns_.values())
        )

    @classmethod
    def _id_from_data(cls, data):
        return tuple(data[key] for key in cls._key_)

    @classmethod
    def _dict_from_id(cls, rowid):
        return dict(zip(cls._key_, rowid))

    @classmethod
    def _make_rows(cls: Type[RowT], *data_rows: DictRow) -> list[RowT]:
        """
        Create or retrieve Row objects for each provided data row.
        If the rows already exist in cache, updates the cached row.
        """
        # TODO: Handle partial row data here somehow?
        rows = [cls(data_row) for data_row in data_rows]
        return rows

    @classmethod
    def _delete_rows(cls, *data_rows):
        """
        Remove the given rows from cache, if they exist.
        May be extended to handle object deletion.
        """
        cache = cls._cache_

        for data_row in data_rows:
            rowid = cls._id_from_data(data_row)
            cache.pop(rowid, None)

    @classmethod
    async def create(cls: Type[RowT], *args, **kwargs) -> RowT:
        return await cls.table.create_row(*args, **kwargs)

    @classmethod
    def fetch_where(cls: Type[RowT], *args, **kwargs):
        return cls.table.fetch_rows_where(*args, **kwargs)

    @classmethod
    async def fetch(cls: Type[RowT], *rowid, cached=True) -> Optional[RowT]:
        """
        Fetch the row with the given id, retrieving from cache where possible.
        """
        row = cls._cache_.get(rowid, None) if cached else None
        if row is None:
            rows = await cls.fetch_where(**cls._dict_from_id(rowid))
            row = rows[0] if rows else None
            if row is None:
                cls._cache_[rowid] = cls(None)
        elif row.data is None:
            row = None

        return row

    @classmethod
    async def fetch_or_create(cls, *rowid, **kwargs):
        """
        Helper method to fetch a row with the given id or fields, or create it if it doesn't exist.
        """
        if rowid:
            row = await cls.fetch(*rowid)
        else:
            rows = await cls.fetch_where(**kwargs).limit(1)
            row = rows[0] if rows else None

        if row is None:
            creation_kwargs = kwargs
            if rowid:
                creation_kwargs.update(cls._dict_from_id(rowid))
            row = await cls.create(**creation_kwargs)
        return row

    async def refresh(self: RowT) -> Optional[RowT]:
        """
        Refresh this Row from data.

        The return value may be `None` if the row was deleted.
        """
        rows = await self.table.select_where(**self._dict_)
        if not rows:
            return None
        else:
            self.data = rows[0]
            return self

    async def update(self: RowT, **values) -> Optional[RowT]:
        """
        Update this Row with the given values.

        Internally passes the provided `values` to the `update` Query.
        The return value may be `None` if the row was deleted.
        """
        data = await self.table.update_where(**self._dict_).set(**values).with_adapter(self._make_rows)
        if not data:
            return None
        else:
            return data[0]

    async def delete(self: RowT) -> Optional[RowT]:
        """
        Delete this Row.
        """
        data = await self.table.delete_where(**self._dict_).with_adapter(self._delete_rows)
        return data[0] if data is not None else None
