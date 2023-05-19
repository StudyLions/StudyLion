from typing import Generic, Type, TypeVar, Optional, overload

from data import RowModel

from .data import ModelData
from .ui import InteractiveSetting
from .base import BaseSetting

from utils.lib import tabulate


T = TypeVar('T', bound=InteractiveSetting)


class SettingDotDict(Generic[T], dict[str, Type[T]]):
    """
    Dictionary structure allowing simple dot access to items.
    """
    __getattr__ = dict.__getitem__  # type: ignore
    __setattr__ = dict.__setitem__  # type: ignore
    __delattr__ = dict.__delitem__  # type: ignore


class SettingGroup:
    """
    A SettingGroup is a collection of settings under one name.
    """
    __initial_settings__: list[Type[InteractiveSetting]] = []

    _title: Optional[str] = None
    _description: Optional[str] = None

    def __init_subclass__(cls, title: Optional[str] = None):
        cls._title = title or cls._title
        cls._description = cls._description or cls.__doc__

        settings: list[Type[InteractiveSetting]] = []
        for item in cls.__dict__.values():
            if isinstance(item, type) and issubclass(item, InteractiveSetting):
                settings.append(item)
        cls.__initial_settings__ = settings

    def __init_settings__(self):
        settings = SettingDotDict()
        for setting in self.__initial_settings__:
            settings[setting.__name__] = setting
        return settings

    def __init__(self, title=None, description=None) -> None:
        self.title: str = title or self._title or self.__class__.__name__
        self.description: str = description or self._description or ""
        self.settings: SettingDotDict[InteractiveSetting] = self.__init_settings__()

    def attach(self, cls: Type[T], name: Optional[str] = None):
        name = name or cls.setting_id
        self.settings[name] = cls
        return cls

    def detach(self, cls):
        return self.settings.pop(cls.__name__, None)

    def update(self, smap):
        self.settings.update(smap.settings)

    def reduce(self, *keys):
        for key in keys:
            self.settings.pop(key, None)
        return

    async def make_setting_table(self, parent_id, **kwargs):
        """
        Convenience method for generating a rendered setting table.
        """
        rows = []
        for setting in self.settings.values():
            if not setting._virtual:
                set = await setting.get(parent_id, **kwargs)
                name = set.display_name
                value = str(set.formatted)
                rows.append((name, value, set.hover_desc))
        table_rows = tabulate(
            *rows,
            row_format="[`{invis}{key:<{pad}}{colon}`](https://lionbot.org \"{field[2]}\")\t{value}"
        )
        return '\n'.join(table_rows)


class ModelSetting(ModelData, BaseSetting):
    ...


class ModelConfig:
    """
    A ModelConfig provides a central point of configuration for any object described by a single Model.

    An instance of a ModelConfig represents configuration for a single object
    (given by a single row of the corresponding Model).

    The ModelConfig also supports registration of non-model configuration,
    to support associated settings (e.g. list-settings) for the object.

    This is an ABC, and must be subclassed for each object-type.
    """
    settings: SettingDotDict
    _model_settings: set
    model: Type[RowModel]

    def __init__(self, parent_id, row, **kwargs):
        self.parent_id = parent_id
        self.row = row
        self.kwargs = kwargs

    @classmethod
    def register_setting(cls, setting_cls):
        """
        Decorator to register a non-model setting as part of the object configuration.

        The setting class may be re-accessed through the `settings` class attr.

        Subclasses may provide alternative access pathways to key non-model settings.
        """
        cls.settings[setting_cls.setting_id] = setting_cls
        return setting_cls

    @classmethod
    def register_model_setting(cls, model_setting_cls):
        """
        Decorator to register a model setting as part of the object configuration.

        The setting class may be accessed through the `settings` class attr.

        A fresh setting instance may also be retrieved (using cached data)
        through the `get` instance method.

        Subclasses are recommended to provide model settings as properties
        for simplified access and type checking.
        """
        cls._model_settings.add(model_setting_cls.setting_id)
        return cls.register_setting(model_setting_cls)

    def get(self, setting_id):
        """
        Retrieve a freshly initialised copy of the given model-setting.

        The given `setting_id` must have been previously registered through `register_model_setting`.
        This uses cached data, and so is not guaranteed to be up-to-date.
        """
        if setting_id not in self._model_settings:
            # TODO: Log
            raise ValueError
        setting_cls = self.settings[setting_id]
        data = setting_cls._read_from_row(self.parent_id, self.row, **self.kwargs)
        return setting_cls(self.parent_id, data, **self.kwargs)


class ModelSettings:
    """
    A ModelSettings instance aggregates multiple `ModelSetting` instances
    bound to the same parent id on a single Model.

    This enables a single point of access
    for settings of a given Model,
    with support for caching or deriving as needed.

    This is an abstract base class,
    and should be subclassed to define the contained settings.
    """
    _settings: SettingDotDict = SettingDotDict()
    model: Type[RowModel]

    def __init__(self, parent_id, row, **kwargs):
        self.parent_id = parent_id
        self.row = row
        self.kwargs = kwargs

    @classmethod
    async def fetch(cls, *parent_id, **kwargs):
        """
        Load an instance of this ModelSetting with the given parent_id
        and setting keyword arguments.
        """
        row = await cls.model.fetch_or_create(*parent_id)
        return cls(parent_id, row, **kwargs)

    @classmethod
    def attach(self, setting_cls):
        """
        Decorator to attach the given setting class to this modelsetting.
        """
        # This violates the interface principle, use structured typing instead?
        if not (issubclass(setting_cls, BaseSetting) and issubclass(setting_cls, ModelData)):
            raise ValueError(
                f"The provided setting class must be `ModelSetting`, not {setting_cls.__class__.__name__}."
            )
        self._settings[setting_cls.setting_id] = setting_cls
        return setting_cls

    def get(self, setting_id):
        setting_cls = self._settings.get(setting_id)
        data = setting_cls._read_from_row(self.parent_id, self.row, **self.kwargs)
        return setting_cls(self.parent_id, data, **self.kwargs)

    def __getitem__(self, setting_id):
        return self.get(setting_id)
