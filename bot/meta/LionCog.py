from discord.ext.commands import Cog


class LionCog(Cog):
    # A set of other cogs that this cog depends on
    depends_on: set['LionCog'] = set()

    async def _inject(self, bot, *args, **kwargs):
        if self.depends_on:
            not_found = {cogname for cogname in self.depends_on if not bot.get_cog(cogname)}
            raise ValueError(f"Could not load cog '{self.__class__.__name__}', dependencies missing: {not_found}")

        return await super()._inject(bot, *args, *kwargs)
