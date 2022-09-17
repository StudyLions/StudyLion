import re
import datetime
import discord
import asyncio

from cmdClient.lib import SafeCancellation
from meta import client, conf
from core import Lion
from data import NULL, NOTNULL
from settings import GuildSettings
from utils.lib import parse_ranges, utc_now

from . import data
# from .module import module


class Tasklist:
    """
    Class representing an interactive updating tasklist.
    """
    max_task_length = 100

    active = {}  # Map (userid, channelid) -> Tasklist
    messages = {}  # Map messageid -> Tasklist

    checkmark = "✔"
    block_size = 15

    next_emoji = conf.emojis.forward
    prev_emoji = conf.emojis.backward
    question_emoji = conf.emojis.question
    cancel_emoji = conf.emojis.cancel
    refresh_emoji = conf.emojis.refresh

    paged_reaction_order = (
        prev_emoji, cancel_emoji, question_emoji, refresh_emoji, next_emoji
    )
    non_paged_reaction_order = (
        question_emoji, cancel_emoji, refresh_emoji
    )

    reaction_hint = "*Press {} for info, {} to exit and  {} to refresh.*".format(
        question_emoji,
        cancel_emoji,
        refresh_emoji
    )

    _re_flags = re.DOTALL | re.IGNORECASE | re.VERBOSE
    add_regex = re.compile(
        r"^(?: (?:add) | \+) \s+ (.+)",
        _re_flags
    )
    delete_regex = re.compile(
        r"^(?: d(?:el(?:ete)?)? | (?: r(?:(?:emove)|m)?) | -) \s* ([0-9, -]+)$",
        _re_flags
    )
    edit_regex = re.compile(
        r"^e(?:dit)? \s+ (\d+ \s+ .+)",
        _re_flags
    )
    check_regex = re.compile(
        r"^(?: c(?:heck)? | (?: done) | (?: complete))\s* ([0-9, -]+)$",
        _re_flags
    )
    uncheck_regex = re.compile(
        r"^(?: u(?:ncheck)? | (?: undone) | (?: uncomplete)) \s* ([0-9, -]+)$",
        _re_flags
    )
    toggle_regex = re.compile(
        r"^([0-9, -]+)$",
        _re_flags
    )
    cancel_regex = re.compile(
        r"^(cancel)|(exit)|(quit)$",
        _re_flags
    )

    interactive_help = """
    Send the following to modify your tasks while the todolist is visible. \
        `<taskids>` may be given as comma separated numbers and ranges.
    `<taskids>` Toggle the status (checked/unchecked) of the provided tasks.
    `add/+ <task>` Add a new TODO `task`. Each line is added as a separate task.
    `d/rm/- <taskids>` Remove the specified tasks.
    `c/check <taskids>` Check (mark complete) the specified tasks.
    `u/uncheck <taskids>` Uncheck (mark incomplete) the specified tasks.
    `cancel` Cancel the interactive tasklist mode.

    **Examples**
    `add Read chapter 1` Adds a new task `Read chapter 1`.
    `e 1 Notes chapter 1` Edit task `1` to `Notes chapter 1`.
    `d 1, 5-7, 9` Deletes tasks `1, 5, 6, 7, 9`.
    `1, 2-5, 9` Toggle the completion status of tasks `1, 2, 3, 4, 5, 9`.

    You may also edit your tasklist at any time with `{prefix}todo` (see `{prefix}help todo`).
    Note that tasks expire after 24 hours.
    """.format(prefix=client.prefix)

    def __init__(self, member, channel, activate=True):
        self.member = member  # Discord Member owning the tasklist
        self.channel = channel  # Discord Channel for display and input

        self.message = None  # Discord Message currently displaying the tasklist

        self.tasklist = []  # Displayed list of Row(tasklist)

        self.pages = []  # Pages to display
        self.current_page = None  # Current displayed page. None means set automatically
        self.show_help = False  # Whether to show a help section in the pages
        self.has_paging = None  # Whether we have added paging reactions

        self._refreshed_at = None  # Timestamp of the last tasklist refresh
        self._deactivation_task = None  # Task for scheduled tasklist deactivation
        self.interaction_lock = asyncio.Lock()  # Lock to ensure interactions execute sequentially
        self._deactivated = False  # Flag for checking deactivation

        if activate:
            # Populate the tasklist
            self._refresh()

            # Add the tasklist to active tasklists
            self.active[(member.id, channel.id)] = self

    @classmethod
    def fetch_or_create(cls, ctx, flags, member, channel):
        tasklist = cls.active.get((member.id, channel.id), None)
        return tasklist if tasklist is not None else cls(member, channel)

    def _refresh(self):
        """
        Update the in-memory tasklist from data and regenerate the pages
        """
        self.tasklist = data.tasklist.fetch_rows_where(
            userid=self.member.id,
            deleted_at=NULL,
            _extra="ORDER BY created_at ASC, taskid ASC"
        )
        self._refreshed_at = datetime.datetime.utcnow()

    async def _format_tasklist(self):
        """
        Generates a sequence of pages from the tasklist
        """
        # Format tasks
        task_strings = [
            "{num:>{numlen}}. [{mark}] {content}".format(
                num=i,
                numlen=((self.block_size * (i // self.block_size + 1) - 1) // 10) + 1,
                mark=self.checkmark if task.completed_at else ' ',
                content=task.content
            )
            for i, task in enumerate(self.tasklist)
        ]

        # Split up tasklist into formatted blocks
        task_pages = [task_strings[i:i+self.block_size] for i in range(0, len(task_strings), self.block_size)]
        task_blocks = [
            "```md\n{}```".format('\n'.join(page)) for page in task_pages
        ]

        # Formatting strings and data
        page_count = len(task_blocks) or 1
        task_count = len(task_strings)
        complete_count = len([task for task in self.tasklist if task.completed_at])

        if task_count > 0:
            title = "TODO list ({}/{} complete)".format(
                complete_count,
                task_count,
                # ((complete_count * 100) // task_count),
            )
            if complete_count == task_count:
                hint = "You have completed all your tasks! Well done!"
            else:
                hint = ""
        else:
            title = "TODO list"
            hint = "Type `add <task>` to start adding tasks! E.g. `add Revise Maths Paper 1`."
            task_blocks = [""]  # Empty page so we can post

        # Create formatted page embeds, adding help if required
        pages = []
        for i, block in enumerate(task_blocks):
            embed = discord.Embed(
                title=title,
                description="{}\n{}\n{}".format(hint, block, self.reaction_hint),
                timestamp=self._refreshed_at
            ).set_author(name=self.member.display_name, icon_url=self.member.avatar_url)

            if page_count > 1:
                embed.set_footer(text="Page {}/{}".format(i+1, page_count))

            if self.show_help:
                embed.add_field(
                    name="Cheatsheet",
                    value=self.interactive_help
                )
            pages.append(embed)

        self.pages = pages
        return pages

    def _adjust_current_page(self):
        """
        Update the current page number to point to a valid page.
        """
        # Calculate or adjust the current page number
        if self.current_page is None:
            # First page with incomplete task, or the first page
            first_incomplete = next((i for i, task in enumerate(self.tasklist) if not task.completed_at), 0)
            self.current_page = first_incomplete // self.block_size
        elif self.current_page >= len(self.pages):
            self.current_page = len(self.pages) - 1
        elif self.current_page < 0:
            self.current_page %= len(self.pages)

    async def _post(self):
        """
        Post the interactive widget, add reactions, and update the message cache
        """
        pages = self.pages

        # Post the page
        message = await self.channel.send(embed=pages[self.current_page])

        # Add the reactions
        self.has_paging = len(pages) > 1
        for emoji in (self.paged_reaction_order if self.has_paging else self.non_paged_reaction_order):
            await message.add_reaction(emoji)

        # Register
        if self.message:
            self.messages.pop(self.message.id, None)

        self.message = message
        self.messages[message.id] = self

    async def _update(self):
        """
        Update the current message with the current page.
        """
        await self.message.edit(embed=self.pages[self.current_page])

    async def update(self, repost=None):
        """
        Update the displayed tasklist.
        If required, delete and repost the tasklist.
        """
        if self._deactivated:
            return

        # Update data and make page list
        self._refresh()
        await self._format_tasklist()
        self._adjust_current_page()

        if self.message and not repost:
            # Read the channel history, see if we need to repost
            height = 0
            async for message in self.channel.history(limit=20):
                if message.id == self.message.id:
                    break

                height += len(message.content.splitlines())
                if message.embeds or message.attachments or height > 20:
                    repost = True
                    break
                if message.id < self.message.id:
                    # Our message was deleted?
                    repost = True
                    break
            else:
                repost = True

            if not repost:
                try:
                    # TODO: Refactor into update method
                    await self._update()
                    # Add or remove paging reactions as required
                    should_have_paging = len(self.pages) > 1

                    if self.has_paging != should_have_paging:
                        try:
                            await self.message.clear_reactions()
                        except discord.HTTPException:
                            pass
                        if should_have_paging:
                            reaction_order = self.paged_reaction_order
                        else:
                            reaction_order = self.non_paged_reaction_order

                        for emoji in reaction_order:
                            await self.message.add_reaction(emoji)
                        self.has_paging = should_have_paging
                except discord.NotFound:
                    self.messages.pop(self.message.id, None)
                    self.message = None
                    repost = True

        if not self.message or repost:
            if self.message:
                # Delete previous message
                try:
                    await self.message.delete()
                except discord.HTTPException:
                    pass
            await self._post()

        asyncio.create_task(self._schedule_deactivation())

    async def deactivate(self, delete=False):
        """
        Delete from active tasklists and message cache, and remove the reactions.
        If `delete` is given, deletes any output message
        """
        self._deactivated = True
        if self._deactivation_task and not self._deactivation_task.cancelled():
            self._deactivation_task.cancel()

        self.active.pop((self.member.id, self.channel.id), None)
        if self.message:
            self.messages.pop(self.message.id, None)
            try:
                if delete:
                    await self.message.delete()
                else:
                    await self.message.clear_reactions()
            except discord.HTTPException:
                pass

    async def _reward_complete(self, *checked_rows):
        # Fetch guild task reward settings
        guild_settings = GuildSettings(self.member.guild.id)
        task_reward = guild_settings.task_reward.value
        task_reward_limit = guild_settings.task_reward_limit.value

        # Select only tasks that haven't been rewarded before
        unrewarded = [task for task in checked_rows if not task['rewarded']]

        if unrewarded:
            # Select tasks to reward up to the limit of rewards
            recent_rewards = data.tasklist_rewards.queries.count_recent_for(self.member.id)
            max_to_reward = max((task_reward_limit - recent_rewards, 0))
            reward_tasks = unrewarded[:max_to_reward]

            rewarding_count = len(reward_tasks)
            # reached_max = (recent_rewards + rewarding_count) >= task_reward_limit
            reward_coins = task_reward * len(reward_tasks)

            if reward_coins:
                # Rewarding process, now that we know what we need to reward
                # Add coins
                user = Lion.fetch(self.member.guild.id, self.member.id)
                user.addCoins(reward_coins, bonus=True)

                # Mark tasks as rewarded
                taskids = [task['taskid'] for task in reward_tasks]
                data.tasklist.update_where(
                    {'rewarded': True},
                    taskid=taskids,
                )

                # Track reward
                data.tasklist_rewards.insert(
                    userid=self.member.id,
                    reward_count=rewarding_count
                )

                # Log reward
                client.log(
                    "Giving '{}' LionCoins to '{}' (uid:{}) for completing TODO tasks.".format(
                        reward_coins,
                        self.member,
                        self.member.id
                    )
                )

                # TODO: Message in channel? Might be too spammy?
                pass

    def _add_tasks(self, *tasks):
        """
        Add provided tasks to the task list
        """
        insert = [
            (self.member.id, task)
            for task in tasks
        ]
        return data.tasklist.insert_many(
            *insert,
            insert_keys=('userid', 'content')
        )

    def _delete_tasks(self, *indexes):
        """
        Delete tasks from the task list
        """
        taskids = [self.tasklist[i].taskid for i in indexes]

        now = utc_now()
        return data.tasklist.update_where(
            {
                'deleted_at': now,
                'last_updated_at': now
            },
            taskid=taskids,
        )

    def _edit_task(self, index, new_content):
        """
        Update the provided task with the new content
        """
        taskid = self.tasklist[index].taskid

        now = utc_now()
        return data.tasklist.update_where(
            {
                'content': new_content,
                'last_updated_at': now
            },
            taskid=taskid,
        )

    def _check_tasks(self, *indexes):
        """
        Mark provided tasks as complete
        """
        taskids = [self.tasklist[i].taskid for i in indexes]

        now = utc_now()
        return data.tasklist.update_where(
            {
                'completed_at': now,
                'last_updated_at': now
            },
            taskid=taskids,
            completed_at=NULL,
        )

    def _uncheck_tasks(self, *indexes):
        """
        Mark provided tasks as incomplete
        """
        taskids = [self.tasklist[i].taskid for i in indexes]

        now = utc_now()
        return data.tasklist.update_where(
            {
                'completed_at': None,
                'last_updated_at': now
            },
            taskid=taskids,
            completed_at=NOTNULL,
        )

    def _index_range_parser(self, userstr):
        """
        Parse user provided task indicies.
        """
        try:
            indexes = parse_ranges(userstr)
        except SafeCancellation:
            raise SafeCancellation(
                "Couldn't parse the provided task numbers! "
                "Please list the task numbers or ranges separated by a comma, e.g. `1, 3, 5-7, 11`."
            ) from None

        return [index for index in indexes if index < len(self.tasklist)]

    async def parse_add(self, userstr):
        """
        Process arguments to an `add` request
        """
        tasks = (line.strip() for line in userstr.splitlines())
        tasks = [task for task in tasks if task]
        if not tasks:
            # TODO: Maybe have interactive input here
            return

        # Fetch accurate count of current tasks
        count = data.tasklist.select_one_where(
            select_columns=("COUNT(*)",),
            userid=self.member.id,
            deleted_at=NULL
        )[0]

        # Fetch maximum allowed count
        max_task_count = GuildSettings(self.member.guild.id).task_limit.value

        # Check if we are exceeding the count
        if count + len(tasks) > max_task_count:
            raise SafeCancellation("Too many tasks! You can have a maximum of `{}` todo items!".format(max_task_count))

        # Check if any task is too long
        if any(len(task) > self.max_task_length for task in tasks):
            raise SafeCancellation("Please keep your tasks under `{}` characters long.".format(self.max_task_length))

        # Finally, add the tasks
        self._add_tasks(*tasks)

        # Set the current page to the last one
        self.current_page = -1

    async def parse_delete(self, userstr):
        """
        Process arguments to a `delete` request
        """
        # Parse provided ranges
        indexes = self._index_range_parser(userstr)

        if indexes:
            self._delete_tasks(*indexes)

    async def parse_toggle(self, userstr):
        """
        Process arguments to a `toggle` request
        """
        # Parse provided ranges
        indexes = self._index_range_parser(userstr)

        to_check = [index for index in indexes if not self.tasklist[index].completed_at]
        to_uncheck = [index for index in indexes if self.tasklist[index].completed_at]

        if to_uncheck:
            self._uncheck_tasks(*to_uncheck)
        if to_check:
            checked = self._check_tasks(*to_check)
            await self._reward_complete(*checked)

    async def parse_check(self, userstr):
        """
        Process arguments to a `check` request
        """
        # Parse provided ranges
        indexes = self._index_range_parser(userstr)

        if indexes:
            checked = self._check_tasks(*indexes)
            await self._reward_complete(*checked)

    async def parse_uncheck(self, userstr):
        """
        Process arguments to an `uncheck` request
        """
        # Parse provided ranges
        indexes = self._index_range_parser(userstr)

        if indexes:
            self._uncheck_tasks(*indexes)

    async def parse_edit(self, userstr):
        """
        Process arguments to an `edit` request
        """
        splits = userstr.split(maxsplit=1)
        if len(splits) < 2 or not splits[0].isdigit():
            raise SafeCancellation("Please provide the task number and the new content, "
                                   "e.g. `edit 1 Biology homework`.")

        index = int(splits[0])
        new_content = splits[1]

        if index >= len(self.tasklist):
            raise SafeCancellation(
                "You do not have a task number `{}` to edit!".format(index)
            )

        if len(new_content) > self.max_task_length:
            raise SafeCancellation("Please keep your tasks under `{}` characters long.".format(self.max_task_length))

        self._edit_task(index, new_content)

        self.current_page = index // self.block_size

    async def handle_reaction(self, reaction, user, added):
        """
        Reaction handler for reactions on our message.
        """
        str_emoji = reaction.emoji
        if added and str_emoji in self.paged_reaction_order:
            # Attempt to remove reaction
            try:
                await self.message.remove_reaction(reaction.emoji, user)
            except discord.HTTPException:
                pass

        old_message_id = self.message.id
        async with self.interaction_lock:
            # Return if the message changed while we were waiting
            if self.message.id != old_message_id:
                return
            if str_emoji == self.next_emoji and user.id == self.member.id:
                self.current_page += 1
                self.current_page %= len(self.pages)
                if self.show_help:
                    self.show_help = False
                    await self._format_tasklist()
                await self._update()
            elif str_emoji == self.prev_emoji and user.id == self.member.id:
                self.current_page -= 1
                self.current_page %= len(self.pages)
                if self.show_help:
                    self.show_help = False
                    await self._format_tasklist()
                await self._update()
            elif str_emoji == self.cancel_emoji and user.id == self.member.id:
                await self.deactivate(delete=True)
            elif str_emoji == self.question_emoji and user.id == self.member.id:
                self.show_help = not self.show_help
                await self._format_tasklist()
                await self._update()
            elif str_emoji == self.refresh_emoji and user.id == self.member.id:
                await self.update()

    async def handle_message(self, message, content=None):
        """
        Message handler for messages from out member, in the correct channel.
        """
        content = content or message.content

        funcmap = {
            self.add_regex: self.parse_add,
            self.delete_regex: self.parse_delete,
            self.check_regex: self.parse_check,
            self.uncheck_regex: self.parse_uncheck,
            self.toggle_regex: self.parse_toggle,
            self.edit_regex: self.parse_edit,
            self.cancel_regex: self.deactivate,
        }
        async with self.interaction_lock:
            for reg, func in funcmap.items():
                matches = re.search(reg, content)
                if matches:
                    try:
                        await func(matches.group(1))
                        await self.update()
                    except SafeCancellation as e:
                        embed = discord.Embed(
                            description=e.msg,
                            colour=discord.Colour.red()
                        )
                        await message.reply(embed=embed)
                    else:
                        try:
                            await message.delete()
                        except discord.HTTPException:
                            pass
                    break

    async def _schedule_deactivation(self):
        """
        Automatically deactivate the tasklist after some time has passed, and many messages have been sent.
        """
        delay = 5 * 10

        # Remove previous scheduled task
        if self._deactivation_task and not self._deactivation_task.cancelled():
            self._deactivation_task.cancel()

        # Schedule a new task
        try:
            self._deactivation_task = asyncio.create_task(asyncio.sleep(delay))
            await self._deactivation_task
        except asyncio.CancelledError:
            return

        # If we don't have a message, nothing to do
        if not self.message:
            return

        # If we were updated in that time, go back to sleep
        if datetime.datetime.utcnow().timestamp() - self._refreshed_at.timestamp() < delay:
            asyncio.create_task(self._schedule_deactivation())
            return

        # Check if lots of content has been sent since
        height = 0
        async for message in self.channel.history(limit=20):
            if message.id == self.message.id:
                break

            height += len(message.content.splitlines())
            if message.embeds or message.attachments:
                height += 10

            if height >= 100:
                break

            if message.id < self.message.id:
                # Our message was deleted?
                return
        else:
            height = 100

        if height >= 100:
            await self.deactivate()
        else:
            asyncio.create_task(self._schedule_deactivation())


@client.add_after_event("message")
async def tasklist_message_handler(client, message):
    key = (message.author.id, message.channel.id)
    if key in Tasklist.active:
        await Tasklist.active[key].handle_message(message)


@client.add_after_event("reaction_add")
async def tasklist_reaction_add_handler(client, reaction, user):
    if user != client.user and reaction.message.id in Tasklist.messages:
        await Tasklist.messages[reaction.message.id].handle_reaction(reaction, user, True)
