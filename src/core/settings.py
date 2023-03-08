from settings.groups import ModelConfig, SettingDotDict

from .data import CoreData


class GuildConfig(ModelConfig):
    settings = SettingDotDict()
    _model_settings = set()
    model = CoreData.Guild


class UserConfig(ModelConfig):
    settings = SettingDotDict()
    _model_settings = set()
    model = CoreData.User
