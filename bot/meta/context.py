from contextvars import ContextVar


class Context:
    __slots__ = (
        'bot',
        'interaction', 'message',
        'guild', 'channel', 'author', 'user'
    )

    def __init__(self, **kwargs):
        self.bot = kwargs.pop('bot', None)

        self.interaction = interaction = kwargs.pop('interaction', None)
        self.message = message = kwargs.pop('message', interaction.message if interaction is not None else None)

        guild = kwargs.pop('guild', None)
        channel = kwargs.pop('channel', None)
        author = kwargs.pop('author', None)

        if message is not None:
            guild = guild or message.guild
            channel = channel or message.channel
            author = author or message.author
        elif interaction is not None:
            guild = guild or interaction.guild
            channel = channel or interaction.channel
            author = author or interaction.user

        self.guild = guild
        self.channel = channel
        self.author = self.user = author

    def log_string(self):
        """Markdown formatted summary for live logging."""
        parts = []
        if self.interaction is not None:
            parts.append(f"<int id={self.interaction.id} type={self.interaction.type.name}>")
        if self.message is not None:
            parts.append(f"<msg id={self.message.id}>")
        if self.author is not None:
            parts.append(f"<user id={self.author.id} name='{self.author.name}'>")
        if self.channel is not None:
            parts.append(f"<chan id={self.channel.id} name='{self.channel.name}'>")
        if self.guild is not None:
            parts.append(f"<guild id={self.guild.id} name='{self.guild.name}'>")

        return " ".join(parts)


context = ContextVar('context', default=Context())
