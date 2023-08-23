from typing import Type
import json

from data import RowModel, Table, ORDER
from meta.logger import log_wrap, set_logging_context


class ModelData:
    """
    Mixin for settings stored in a single row and column of a Model.
    Assumes that the parent_id is the identity key of the Model.

    This does not create a reference to the Row.
    """
    # Table storing the desired data
    _model: Type[RowModel]

    # Column with the desired data
    _column: str

    # Whether to create a row if not found
    _create_row = False

    # High level data cache to use, leave as None to disable cache.
    _cache = None  # Map[id -> value]

    @classmethod
    def _read_from_row(cls, parent_id, row, **kwargs):
        data = row[cls._column]

        if cls._cache is not None:
            cls._cache[parent_id] = data

        return data

    @classmethod
    async def _reader(cls, parent_id, use_cache=True, **kwargs):
        """
        Read in the requested column associated to the parent id.
        """
        if cls._cache is not None and parent_id in cls._cache and use_cache:
            return cls._cache[parent_id]

        model = cls._model
        if cls._create_row:
            row = await model.fetch_or_create(parent_id)
        else:
            row = await model.fetch(parent_id)
        data = row[cls._column] if row else None

        if cls._cache is not None:
            cls._cache[parent_id] = data

        return data

    @classmethod
    async def _writer(cls, parent_id, data, **kwargs):
        """
        Write the provided entry to the table.
        This does *not* create the row if it does not exist.
        It only updates.
        """
        # TODO: Better way of getting the key?
        # TODO: Transaction
        if not isinstance(parent_id, tuple):
            parent_id = (parent_id, )
        model = cls._model
        rows = await model.table.update_where(
            **model._dict_from_id(parent_id)
        ).set(
            **{cls._column: data}
        )
        # If we didn't update any rows, create a new row
        if not rows:
            await model.fetch_or_create(**model._dict_from_id(parent_id), **{cls._column: data})

        if cls._cache is not None:
            cls._cache[parent_id] = data


class ListData:
    """
    Mixin for list types implemented on a Table.
    Implements a reader and writer.
    This assumes the list is the only data stored in the table,
    and removes list entries by deleting rows.
    """
    setting_id: str

    # Table storing the setting data
    _table_interface: Table

    # Name of the column storing the id
    _id_column: str

    # Name of the column storing the data to read
    _data_column: str

    # Name of column storing the order index to use, if any. Assumed to be Serial on writing.
    _order_column: str
    _order_type: ORDER = ORDER.ASC

    # High level data cache to use, set to None to disable cache.
    _cache = None  # Map[id -> value]

    @classmethod
    @log_wrap(isolate=True)
    async def _reader(cls, parent_id, use_cache=True, **kwargs):
        """
        Read in all entries associated to the given id.
        """
        set_logging_context(action="Read cls.setting_id")
        if cls._cache is not None and parent_id in cls._cache and use_cache:
            return cls._cache[parent_id]

        table = cls._table_interface  # type: Table
        query = table.select_where(**{cls._id_column: parent_id}).select(cls._data_column)
        if cls._order_column:
            query.order_by(cls._order_column, direction=cls._order_type)

        rows = await query
        data = [row[cls._data_column] for row in rows]

        if cls._cache is not None:
            cls._cache[parent_id] = data

        return data

    @classmethod
    @log_wrap(isolate=True)
    async def _writer(cls, id, data, add_only=False, remove_only=False, **kwargs):
        """
        Write the provided list to storage.
        """
        set_logging_context(action="Write cls.setting_id")
        table = cls._table_interface
        async with table.connector.connection() as conn:
            table.connector.conn = conn
            async with conn.transaction():
                # Handle None input as an empty list
                if data is None:
                    data = []

                current = await cls._reader(id, use_cache=False, **kwargs)
                if not cls._order_column and (add_only or remove_only):
                    to_insert = [item for item in data if item not in current] if not remove_only else []
                    to_remove = data if remove_only else (
                        [item for item in current if item not in data] if not add_only else []
                    )

                    # Handle required deletions
                    if to_remove:
                        params = {
                            cls._id_column: id,
                            cls._data_column: to_remove
                        }
                        await table.delete_where(**params)

                    # Handle required insertions
                    if to_insert:
                        columns = (cls._id_column, cls._data_column)
                        values = [(id, value) for value in to_insert]
                        await table.insert_many(columns, *values)

                    if cls._cache is not None:
                        new_current = [item for item in current + to_insert if item not in to_remove]
                        cls._cache[id] = new_current
                else:
                    # Remove all and add all to preserve order
                    delete_params = {cls._id_column: id}
                    await table.delete_where(**delete_params)

                    if data:
                        columns = (cls._id_column, cls._data_column)
                        values = [(id, value) for value in data]
                        await table.insert_many(columns, *values)

                    if cls._cache is not None:
                        cls._cache[id] = data


class KeyValueData:
    """
    Mixin for settings implemented in a Key-Value table.
    The underlying table should have a Unique constraint on the `(_id_column, _key_column)` pair.
    """
    _table_interface: Table

    _id_column: str

    _key_column: str

    _value_column: str

    _key: str

    @classmethod
    async def _reader(cls, id, **kwargs):
        params = {
            cls._id_column: id,
            cls._key_column: cls._key
        }

        row = await cls._table_interface.select_one_where(**params).select(cls._value_column)
        data = row[cls._value_column] if row else None

        if data is not None:
            data = json.loads(data)

        return data

    @classmethod
    async def _writer(cls, id, data, **kwargs):
        params = {
            cls._id_column: id,
            cls._key_column: cls._key
        }
        if data is not None:
            values = {
                cls._value_column: json.dumps(data)
            }
            rows = await cls._table_interface.update_where(**params).set(**values)
            if not rows:
                await cls._table_interface.insert_many(
                    (cls._id_column, cls._key_column, cls._value_column),
                    (id, cls._key, json.dumps(data))
                )
        else:
            await cls._table_interface.delete_where(**params)


# class UserInputError(SafeCancellation):
#     pass
