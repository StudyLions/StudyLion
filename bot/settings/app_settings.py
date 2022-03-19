import settings
from utils.lib import DotDict

class AppSettings(settings.ObjectSettings):
    settings = DotDict()
