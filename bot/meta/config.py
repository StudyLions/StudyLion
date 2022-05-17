from discord import PartialEmoji
import configparser as cfgp

from .args import args


class configEmoji(PartialEmoji):
    __slots__ = ('fallback',)

    def __init__(self, *args, fallback=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fallback = fallback

    @classmethod
    def from_str(cls, emojistr: str):
        """
        Parses emoji strings of one of the following forms
            `<a:name:id> or fallback`
            `<:name:id> or fallback`
            `<a:name:id>`
            `<:name:id>`
        """
        splits = emojistr.rsplit(' or ', maxsplit=1)

        fallback = splits[1] if len(splits) > 1 else None
        emojistr = splits[0].strip('<> ')
        animated, name, id = emojistr.split(':')
        return cls(
            name=name,
            fallback=PartialEmoji(name=fallback),
            animated=bool(animated),
            id=int(id)
        )


class MapDotProxy:
    """
    Allows dot access to an underlying Mappable object.
    """
    __slots__ = ("_map", "_converter")

    def __init__(self, mappable, converter=None):
        self._map = mappable
        self._converter = converter

    def __getattribute__(self, key):
        _map = object.__getattribute__(self, '_map')
        if key == '_map':
            return _map
        if key in _map:
            _converter = object.__getattribute__(self, '_converter')
            if _converter:
                return _converter(_map[key])
            else:
                return _map[key]
        else:
            return object.__getattribute__(_map, key)

    def __getitem__(self, key):
        return self._map.__getitem__(key)


class Conf:
    def __init__(self, configfile, section_name="DEFAULT"):
        self.configfile = configfile

        self.config = cfgp.ConfigParser(
            converters={
                "intlist": self._getintlist,
                "list": self._getlist,
                "emoji": configEmoji.from_str,
            }
        )
        self.config.read(configfile)

        self.section_name = section_name if section_name in self.config else 'DEFAULT'

        self.default = self.config["DEFAULT"]
        self.section = MapDotProxy(self.config[self.section_name])
        self.bot = self.section

        # Config file recursion, read in configuration files specified in every "ALSO_READ" key.
        more_to_read = self.section.getlist("ALSO_READ", [])
        read = set()
        while more_to_read:
            to_read = more_to_read.pop(0)
            read.add(to_read)
            self.config.read(to_read)
            new_paths = [path for path in self.section.getlist("ALSO_READ", [])
                         if path not in read and path not in more_to_read]
            more_to_read.extend(new_paths)

        self.emojis = MapDotProxy(
            self.config['EMOJIS'] if 'EMOJIS' in self.config else self.section,
            converter=configEmoji.from_str
        )

        global conf
        conf = self

    def __getitem__(self, key):
        return self.section[key].strip()

    def __getattr__(self, section):
        return self.config[section]

    def get(self, name, fallback=None):
        result = self.section.get(name, fallback)
        return result.strip() if result else result

    def _getintlist(self, value):
        return [int(item.strip()) for item in value.split(',')]

    def _getlist(self, value):
        return [item.strip() for item in value.split(',')]

    def write(self):
        with open(self.configfile, 'w') as conffile:
            self.config.write(conffile)


conf = Conf(args.config)
