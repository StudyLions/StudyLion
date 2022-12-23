import discord
from discord import app_commands


class LocalString:
    def __init__(self, string):
        self.string = string

    def as_string(self):
        return self.string


_ = LocalString
