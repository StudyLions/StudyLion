from .module import module

from settings import UserSettings


@module.cmd(
    "mytz",
    group="Personal Settings",
    desc=("Timezone used to display prompts. "
          "(Currently {ctx.author_settings.timezone.formatted})"),
)
async def cmd_mytimezone(ctx):
    """
    Usage``:
        {prefix}mytz
        {prefix}mytz <tz name>
    Setting Description:
        {ctx.author_settings.settings.timezone.long_desc}
    Accepted Values:
        Timezone names must be from the "TZ Database Name" column of \
        [this list](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones).
        For example, `Europe/London`, `Australia/Melbourne`, or `America/New_York`.
        Partial names are also accepted.
    Examples``:
        {prefix}mytz Europe/London
        {prefix}mytz London
    """
    await UserSettings.settings.timezone.command(ctx, ctx.author.id)
