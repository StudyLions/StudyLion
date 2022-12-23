from settings.groups import ModelSettings, SettingDotDict
from .data import CoreData


class GuildSettings(ModelSettings):
    _settings = SettingDotDict()
    model = CoreData.Guild
