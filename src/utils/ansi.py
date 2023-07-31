"""
Minimal library for making Discord Ansi colour codes.
"""
from enum import StrEnum


PREFIX = u'\u001b'


class TextColour(StrEnum):
    Gray = '30'
    Red = '31'
    Green = '32'
    Yellow = '33'
    Blue = '34'
    Pink = '35'
    Cyan = '36'
    White = '37'

    def __str__(self) -> str:
        return AnsiColour(fg=self).as_str()

    def __call__(self):
        return AnsiColour(fg=self)


class BgColour(StrEnum):
    FireflyDarkBlue = '40'
    Orange = '41'
    MarbleBlue = '42'
    GrayTurq = '43'
    Gray = '44'
    Indigo = '45'
    LightGray = '46'
    White = '47'

    def __str__(self) -> str:
        return AnsiColour(bg=self).as_str()

    def __call__(self):
        return AnsiColour(bg=self)


class Format(StrEnum):
    NORMAL = '0'
    BOLD = '1'
    UNDERLINE = '4'
    NOOP = '9'

    def __str__(self) -> str:
        return AnsiColour(self).as_str()

    def __call__(self):
        return AnsiColour(self)


class AnsiColour:
    def __init__(self, *flags, fg=None, bg=None):
        self.text_colour = fg
        self.background_colour = bg
        self.reset = (Format.NORMAL in flags)
        self._flags = set(flags)
        self._flags.discard(Format.NORMAL)

    @property
    def flags(self):
        return (*((Format.NORMAL,) if self.reset else ()), *self._flags)

    def as_str(self):
        parts = []
        if self.reset:
            parts.append(Format.NORMAL)
        elif not self.flags:
            parts.append(Format.NOOP)

        parts.extend(self._flags)

        for c in (self.text_colour, self.background_colour):
            if c is not None:
                parts.append(c)

        partstr = ';'.join(part.value for part in parts)
        return f"{PREFIX}[{partstr}m"  # ]

    def __str__(self):
        return self.as_str()

    def __add__(self, obj: 'AnsiColour'):
        text_colour = obj.text_colour or self.text_colour
        background_colour = obj.background_colour or self.background_colour
        flags = (*self.flags, *obj.flags)
        return AnsiColour(*flags, fg=text_colour, bg=background_colour)


RESET = AnsiColour(Format.NORMAL)
BOLD = AnsiColour(Format.BOLD)
UNDERLINE = AnsiColour(Format.UNDERLINE)
