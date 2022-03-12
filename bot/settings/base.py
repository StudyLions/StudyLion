import discord
from cmdClient.cmdClient import cmdClient
from cmdClient.lib import SafeCancellation
from cmdClient.Check import Check

from utils.lib import prop_tabulate, DotDict

from LionContext import LionContext as Context

from meta import client
from data import Table, RowTable


class Setting:
    """
    Abstract base class describing a stored configuration setting.
    A setting consists of logic to load the setting from storage,
    present it in a readable form, understand user entered values,
    and write it again in storage.
    Additionally, the setting has attributes attached describing
    the setting in a user-friendly manner for display purposes.
    """
    attr_name: str = None  # Internal attribute name for the setting
    _default: ... = None  # Default data value for the setting.. this may be None if the setting overrides 'default'.

    write_ward: Check = None  # Check that must be passed to write the setting. Not implemented internally.

    # Configuration interface descriptions
    display_name: str = None  # User readable name of the setting
    desc: str = None  # User readable brief description of the setting
    long_desc: str = None  # User readable long description of the setting
    accepts: str = None  # User readable description of the acceptable values

    def __init__(self, id, data: ..., **kwargs):
        self.client: cmdClient = client
        self.id = id
        self._data = data

    # Configuration embeds
    @property
    def embed(self):
        """
        Discord Embed showing an information summary about the setting.
        """
        embed = discord.Embed(
            title="Configuration options for `{}`".format(self.display_name),
        )
        fields = ("Current value", "Default value", "Accepted input")
        values = (self.formatted or "Not Set",
                  self._format_data(self.id, self.default) or "None",
                  self.accepts)
        table = prop_tabulate(fields, values)
        embed.description = "{}\n{}".format(self.long_desc.format(self=self, client=self.client), table)
        return embed

    async def widget(self, ctx: Context, **kwargs):
        """
        Show the setting widget for this setting.
        By default this displays the setting embed.
        Settings may override this if they need more complex widget context or logic.
        """
        return await ctx.reply(embed=self.embed)

    @property
    def summary(self):
        """
        Formatted summary of the data.
        May be implemented in `_format_data(..., summary=True, ...)` or overidden.
        """
        return self._format_data(self.id, self.data, summary=True)

    @property
    def success_response(self):
        """
        Response message sent when the setting has successfully been updated.
        """
        return "Setting Updated!"

    # Instance generation
    @classmethod
    def get(cls, id: int, **kwargs):
        """
        Return a setting instance initialised from the stored value.
        """
        data = cls._reader(id, **kwargs)
        return cls(id, data, **kwargs)

    @classmethod
    async def parse(cls, id: int, ctx: Context, userstr: str, **kwargs):
        """
        Return a setting instance initialised from a parsed user string.
        """
        data = await cls._parse_userstr(ctx, id, userstr, **kwargs)
        return cls(id, data, **kwargs)

    # Main interface
    @property
    def data(self):
        """
        Retrieves the current internal setting data if it is set, otherwise the default data
        """
        return self._data if self._data is not None else self.default

    @data.setter
    def data(self, new_data):
        """
        Sets the internal setting data and writes the changes.
        """
        self._data = new_data
        self.write()

    @property
    def default(self):
        """
        Retrieves the default value for this setting.
        Settings should override this if the default depends on the object id.
        """
        return self._default

    @property
    def value(self):
        """
        Discord-aware object or objects associated with the setting.
        """
        return self._data_to_value(self.id, self.data)

    @value.setter
    def value(self, new_value):
        """
        Setter which reads the discord-aware object, converts it to data, and writes it.
        """
        self._data = self._data_from_value(self.id, new_value)
        self.write()

    @property
    def formatted(self):
        """
        User-readable form of the setting.
        """
        return self._format_data(self.id, self.data)

    def write(self, **kwargs):
        """
        Write value to the database.
        For settings which override this,
        ensure you handle deletion of values when internal data is None.
        """
        self._writer(self.id, self._data, **kwargs)

    # Raw converters
    @classmethod
    def _data_from_value(cls, id: int, value, **kwargs):
        """
        Convert a high-level setting value to internal data.
        Must be overriden by the setting.
        Be aware of None values, these should always pass through as None
        to provide an unsetting interface.
        """
        raise NotImplementedError

    @classmethod
    def _data_to_value(cls, id: int, data: ..., **kwargs):
        """
        Convert internal data to high-level setting value.
        Must be overriden by the setting.
        """
        raise NotImplementedError

    @classmethod
    async def _parse_userstr(cls, ctx: Context, id: int, userstr: str, **kwargs):
        """
        Parse user provided input into internal data.
        Must be overriden by the setting if the setting is user-configurable.
        """
        raise NotImplementedError

    @classmethod
    def _format_data(cls, id: int, data: ..., **kwargs):
        """
        Convert internal data into a formatted user-readable string.
        Must be overriden by the setting if the setting is user-viewable.
        """
        raise NotImplementedError

    # Database access classmethods
    @classmethod
    def _reader(cls, id: int, **kwargs):
        """
        Read a setting from storage and return setting data or None.
        Must be overriden by the setting.
        """
        raise NotImplementedError

    @classmethod
    def _writer(cls, id: int, data: ..., **kwargs):
        """
        Write provided setting data to storage.
        Must be overriden by the setting unless the `write` method is overidden.
        If the data is None, the setting is empty and should be unset.
        """
        raise NotImplementedError

    @classmethod
    async def command(cls, ctx, id, flags=()):
        """
        Standardised command viewing/setting interface for the setting.
        """
        if not ctx.args and not ctx.msg.attachments:
            # View config embed for provided cls
            await cls.get(id).widget(ctx, flags=flags)
        else:
            # Check the write ward
            if cls.write_ward and not await cls.write_ward.run(ctx):
                await ctx.error_reply(cls.write_ward.msg)
            else:
                # Attempt to set config cls
                try:
                    cls = await cls.parse(id, ctx, ctx.args)
                except UserInputError as e:
                    await ctx.reply(embed=discord.Embed(
                        description="{} {}".format('❌', e.msg),
                        Colour=discord.Colour.red()
                    ))
                else:
                    cls.write()
                    await ctx.reply(embed=discord.Embed(
                        description="{} {}".format('✅', cls.success_response),
                        Colour=discord.Colour.green()
                    ))

    @classmethod
    def init_task(self, client):
        """
        Initialisation task to be excuted during client initialisation.
        May be used for e.g. populating a cache or required client setup.

        Main application must execute the initialisation task before the setting is used.
        Further, the task must always be executable, if the setting is loaded.
        Conditional initalisation should go in the relevant module's init tasks.
        """
        return None


class ObjectSettings:
    """
    Abstract class representing a linked collection of settings for a single object.
    Initialised settings are provided as instance attributes in the form of properties.
    """
    __slots__ = ('id', 'params')

    settings: DotDict = None

    def __init__(self, id, **kwargs):
        self.id = id
        self.params = tuple(kwargs.items())

    @classmethod
    def _setting_property(cls, setting):
        def wrapped_setting(self):
            return setting.get(self.id, **dict(self.params))
        return wrapped_setting

    @classmethod
    def attach_setting(cls, setting: Setting):
        name = setting.attr_name or setting.__name__
        setattr(cls, name, property(cls._setting_property(setting)))
        cls.settings[name] = setting
        return setting

    def tabulated(self):
        """
        Convenience method to provide a complete setting property-table.
        """
        formatted = {
            setting.display_name: setting.get(self.id, **dict(self.params)).formatted
            for name, setting in self.settings.items()
        }
        return prop_tabulate(*zip(*formatted.items()))


class ColumnData:
    """
    Mixin for settings stored in a single row and column of a Table.
    Intended to be used with tables where the only primary key is the object id.
    """
    # Table storing the desired data
    _table_interface: Table = None

    # Name of the column storing the setting object id
    _id_column: str = None

    # Name of the column with the desired data
    _data_column: str = None

    # Whether to use create a row if not found (only applies to TableRow)
    _create_row = False

    # Whether to upsert or update for updates
    _upsert: bool = True

    # High level data cache to use, set to None to disable cache.
    _cache = None  # Map[id -> value]

    @classmethod
    def _reader(cls, id: int, use_cache=True, **kwargs):
        """
        Read in the requested entry associated to the id.
        Supports reading cached values from a `RowTable`.
        """
        if cls._cache is not None and id in cls._cache and use_cache:
            return cls._cache[id]

        table = cls._table_interface
        if isinstance(table, RowTable) and cls._id_column == table.id_col:
            if cls._create_row:
                row = table.fetch_or_create(id)
            else:
                row = table.fetch(id)
            data = row.data[cls._data_column] if row else None
        else:
            params = {
                "select_columns": (cls._data_column,),
                cls._id_column: id
            }
            row = table.select_one_where(**params)
            data = row[cls._data_column] if row else None

        if cls._cache is not None:
            cls._cache[id] = data

        return data

    @classmethod
    def _writer(cls, id: int, data: ..., **kwargs):
        """
        Write the provided entry to the table, allowing replacements.
        """
        table = cls._table_interface
        params = {
            cls._id_column: id
        }
        values = {
            cls._data_column: data
        }

        # Update data
        if cls._upsert:
            # Upsert data
            table.upsert(
                constraint=cls._id_column,
                **params,
                **values
            )
        else:
            # Update data
            table.update_where(values, **params)

        if cls._cache is not None:
            cls._cache[id] = data


class ListData:
    """
    Mixin for list types implemented on a Table.
    Implements a reader and writer.
    This assumes the list is the only data stored in the table,
    and removes list entries by deleting rows.
    """
    # Table storing the setting data
    _table_interface: Table = None

    # Name of the column storing the id
    _id_column: str = None

    # Name of the column storing the data to read
    _data_column: str = None

    # Name of column storing the order index to use, if any. Assumed to be Serial on writing.
    _order_column: str = None
    _order_type: str = "ASC"

    # High level data cache to use, set to None to disable cache.
    _cache = None  # Map[id -> value]

    @classmethod
    def _reader(cls, id: int, use_cache=True, **kwargs):
        """
        Read in all entries associated to the given id.
        """
        if cls._cache is not None and id in cls._cache and use_cache:
            return cls._cache[id]

        table = cls._table_interface  # type: Table
        params = {
            "select_columns": [cls._data_column],
            cls._id_column: id
        }
        if cls._order_column:
            params['_extra'] = "ORDER BY {} {}".format(cls._order_column, cls._order_type)

        rows = table.select_where(**params)
        data = [row[cls._data_column] for row in rows]

        if cls._cache is not None:
            cls._cache[id] = data

        return data

    @classmethod
    def _writer(cls, id: int, data: ..., add_only=False, remove_only=False, **kwargs):
        """
        Write the provided list to storage.
        """
        # TODO: Transaction lock on the table so this is atomic
        # Or just use the connection context manager

        table = cls._table_interface  # type: Table

        # Handle None input as an empty list
        if data is None:
            data = []

        current = cls._reader(id, **kwargs)
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
                table.delete_where(**params)

            # Handle required insertions
            if to_insert:
                columns = (cls._id_column, cls._data_column)
                values = [(id, value) for value in to_insert]
                table.insert_many(*values, insert_keys=columns)

            if cls._cache is not None:
                new_current = [item for item in current + to_insert if item not in to_remove]
                cls._cache[id] = new_current
        else:
            # Remove all and add all to preserve order
            # TODO: This really really should be atomic if anything else reads this
            delete_params = {cls._id_column: id}
            table.delete_where(**delete_params)

            if data:
                columns = (cls._id_column, cls._data_column)
                values = [(id, value) for value in data]
                table.insert_many(*values, insert_keys=columns)

            if cls._cache is not None:
                cls._cache[id] = data


class UserInputError(SafeCancellation):
    pass
