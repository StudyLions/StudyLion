from typing import Generic, TypeVar, Type, Optional, overload


"""
Setting metclass?
Parse setting docstring to generate default info?
Or just put it in the decorator we are already using
"""


# Typing using Generic[parent_id_type, data_type, value_type]
# value generic, could be Union[?, UNSET]
ParentID = TypeVar('ParentID')
SettingData = TypeVar('SettingData')
SettingValue = TypeVar('SettingValue')

T = TypeVar('T', bound='BaseSetting')


class BaseSetting(Generic[ParentID, SettingData, SettingValue]):
    """
    Abstract base class describing a stored configuration setting.
    A setting consists of logic to load the setting from storage,
    present it in a readable form, understand user entered values,
    and write it again in storage.
    Additionally, the setting has attributes attached describing
    the setting in a user-friendly manner for display purposes.
    """
    setting_id: str  # Unique source identifier for the setting

    _default: Optional[SettingData] = None  # Default data value for the setting

    def __init__(self, parent_id: ParentID, data: Optional[SettingData], **kwargs):
        self.parent_id = parent_id
        self._data = data
        self.kwargs = kwargs

    # Instance generation
    @classmethod
    async def get(cls: Type[T], parent_id: ParentID, **kwargs) -> T:
        """
        Return a setting instance initialised from the stored value, associated with the given parent id.
        """
        data = await cls._reader(parent_id, **kwargs)
        return cls(parent_id, data, **kwargs)

    # Main interface
    @property
    def data(self) -> Optional[SettingData]:
        """
        Retrieves the current internal setting data if it is set, otherwise the default data
        """
        return self._data if self._data is not None else self.default

    @data.setter
    def data(self, new_data: Optional[SettingData]):
        """
        Sets the internal raw data.
        Does not write the changes.
        """
        self._data = new_data

    @property
    def default(self) -> Optional[SettingData]:
        """
        Retrieves the default value for this setting.
        Settings should override this if the default depends on the object id.
        """
        return self._default

    @property
    def value(self) -> SettingValue:  # Actually optional *if* _default is None
        """
        Context-aware object or objects associated with the setting.
        """
        return self._data_to_value(self.parent_id, self.data)  # type: ignore

    @value.setter
    def value(self, new_value: Optional[SettingValue]):
        """
        Setter which reads the discord-aware object and converts it to data.
        Does not write the new value.
        """
        self._data = self._data_from_value(self.parent_id, new_value)

    async def write(self, **kwargs) -> None:
        """
        Write current data to the database.
        For settings which override this,
        ensure you handle deletion of values when internal data is None.
        """
        await self._writer(self.parent_id, self._data, **kwargs)

    # Raw converters
    @overload
    @classmethod
    def _data_from_value(cls: Type[T], parent_id: ParentID, value: SettingValue, **kwargs) -> SettingData:
        ...

    @overload
    @classmethod
    def _data_from_value(cls: Type[T], parent_id: ParentID, value: None, **kwargs) -> None:
        ...

    @classmethod
    def _data_from_value(
        cls: Type[T], parent_id: ParentID, value: Optional[SettingValue], **kwargs
    ) -> Optional[SettingData]:
        """
        Convert a high-level setting value to internal data.
        Must be overridden by the setting.
        Be aware of UNSET values, these should always pass through as None
        to provide an unsetting interface.
        """
        raise NotImplementedError

    @overload
    @classmethod
    def _data_to_value(cls: Type[T], parent_id: ParentID, data: SettingData, **kwargs) -> SettingValue:
        ...

    @overload
    @classmethod
    def _data_to_value(cls: Type[T], parent_id: ParentID, data: None, **kwargs) -> None:
        ...

    @classmethod
    def _data_to_value(
        cls: Type[T], parent_id: ParentID, data: Optional[SettingData], **kwargs
    ) -> Optional[SettingValue]:
        """
        Convert internal data to high-level setting value.
        Must be overriden by the setting.
        """
        raise NotImplementedError

    # Database access
    @classmethod
    async def _reader(cls: Type[T], parent_id: ParentID, **kwargs) -> Optional[SettingData]:
        """
        Retrieve the setting data associated with the given parent_id.
        May be None if the setting is not set.
        Must be overridden by the setting.
        """
        raise NotImplementedError

    @classmethod
    async def _writer(cls: Type[T], parent_id: ParentID, data: Optional[SettingData], **kwargs) -> None:
        """
        Write provided setting data to storage.
        Must be overridden by the setting unless the `write` method is overridden.
        If the data is None, the setting is UNSET and should be deleted.
        """
        raise NotImplementedError

    @classmethod
    async def setup(cls, bot):
        """
        Initialisation task to be executed during client initialisation.
        May be used for e.g. populating a cache or required client setup.

        Main application must execute the initialisation task before the setting is used.
        Further, the task must always be executable, if the setting is loaded.
        Conditional initialisation should go in the relevant module's init tasks.
        """
        return None
