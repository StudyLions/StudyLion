from typing import Generic, Type, TypeVar, Optional
from .ui import InteractiveSetting

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
        name = name or cls.__name__
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

    async def make_setting_table(self, parent_id):
        """
        Convenience method for generating a rendered setting table.
        """
        rows = []
        for setting in self.settings.values():
            name = f"{setting.display_name}"
            set = await setting.get(parent_id)
            value = set.formatted
            rows.append((name, value, set.hover_desc))
        table_rows = tabulate(
            *rows,
            row_format="[`{invis}{key:<{pad}}{colon}`](https://lionbot.org \"{field[2]}\")\t{value}"
        )
        return '\n'.join(table_rows)
