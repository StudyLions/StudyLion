from typing import Optional
from psycopg.rows import DictRow
from psycopg import sql

from . import queries as q
from .connector import Connector
from .registry import Registry


class Table:
    """
    Transparent interface to a single table structure in the database.
    Contains standard methods to access the table.
    """

    def __init__(self, name, *args, schema='public', **kwargs):
        self.name: str = name
        self.schema: str = schema
        self.connector: Connector = None

    @property
    def identifier(self):
        if self.schema == 'public':
            return sql.Identifier(self.name)
        else:
            return sql.Identifier(self.schema, self.name)

    def bind(self, connector: Connector):
        self.connector = connector
        return self

    def attach_to(self, registry: Registry):
        self._registry = registry
        return self

    def _many_query_adapter(self, *data: DictRow) -> tuple[DictRow, ...]:
        return data

    def _single_query_adapter(self, *data: DictRow) -> Optional[DictRow]:
        if data:
            return data[0]
        else:
            return None

    def _delete_query_adapter(self, *data: DictRow) -> tuple[DictRow, ...]:
        return data

    def select_where(self, *args, **kwargs) -> q.Select[tuple[DictRow, ...]]:
        return q.Select(
            self.identifier,
            row_adapter=self._many_query_adapter,
            connector=self.connector
        ).where(*args, **kwargs)

    def select_one_where(self, *args, **kwargs) -> q.Select[DictRow]:
        return q.Select(
            self.identifier,
            row_adapter=self._single_query_adapter,
            connector=self.connector
        ).where(*args, **kwargs)

    def update_where(self, *args, **kwargs) -> q.Update[tuple[DictRow, ...]]:
        return q.Update(
            self.identifier,
            row_adapter=self._many_query_adapter,
            connector=self.connector
        ).where(*args, **kwargs)

    def delete_where(self, *args, **kwargs) -> q.Delete[tuple[DictRow, ...]]:
        return q.Delete(
            self.identifier,
            row_adapter=self._many_query_adapter,
            connector=self.connector
        ).where(*args, **kwargs)

    def insert(self, **column_values) -> q.Insert[DictRow]:
        return q.Insert(
            self.identifier,
            row_adapter=self._single_query_adapter,
            connector=self.connector
        ).insert(column_values.keys(), column_values.values())

    def insert_many(self, *args, **kwargs) -> q.Insert[tuple[DictRow, ...]]:
        return q.Insert(
            self.identifier,
            row_adapter=self._many_query_adapter,
            connector=self.connector
        ).insert(*args, **kwargs)

#    def update_many(self, *args, **kwargs):
#        with self.conn:
#            return update_many(self.identifier, *args, **kwargs)

#    def upsert(self, *args, **kwargs):
#        return upsert(self.identifier, *args, **kwargs)
