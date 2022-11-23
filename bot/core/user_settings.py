from settings.groups import ModelSettings, SettingDotDict
from .data import CoreData


class UserSettings(ModelSettings):
    _settings = SettingDotDict()
    model = CoreData.User
