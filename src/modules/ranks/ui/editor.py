from typing import Optional

import discord
from discord.ui.text_input import TextInput, TextStyle

from meta import LionBot
from meta.errors import UserInputError
from core.data import RankType

from utils.ui import FastModal, error_handler_for, ModalRetryUI
from utils.lib import parse_duration, replace_multiple

from .. import babel, logger
from ..data import AnyRankData
from ..utils import format_stat_range, rank_model_from_type, rank_message_keys

_p = babel._p


class RankEditor(FastModal):
    """
    Create or edit a single Rank.
    """
    role_name: TextInput = TextInput(
        label='ROLE_NAME_PLACHOLDER',
        max_length=128,
        required=True
    )

    def role_name_setup(self):
        self.role_name.label = self.bot.translator.t(_p(
            'ui:rank_editor|input:role_name|label',
            "Role Name"
        ))
        self.role_name.placeholder = self.bot.translator.t(_p(
            'ui:rank_editor|input:role_name|placeholder',
            "Name of the awarded guild role"
        ))

    def role_name_parse(self) -> str:
        return self.role_name.value

    role_colour: TextInput = TextInput(
        label='ROLE_COLOUR_PLACEHOLDER',
        min_length=7,
        max_length=16,
        required=False
    )

    def role_colour_setup(self):
        self.role_colour.label = self.bot.translator.t(_p(
            'ui:rank_editor|input:role_colour|label',
            "Role Colour"
        ))
        self.role_colour.placeholder = self.bot.translator.t(_p(
            'ui:rank_editor|input:role_colour|placeholder',
            "Colour of the awarded guild role, e.g. #AB1321"
        ))

    def role_colour_parse(self) -> discord.Colour:
        t = self.bot.translator.t
        if self.role_colour.value:
            try:
                colour = discord.Colour.from_str(self.role_colour.value)
            except ValueError:
                raise UserInputError(
                    _msg=t(_p(
                        'ui:rank_editor|input:role_colour|error:parse',
                        "`role_colour`: Could not parse colour! Please use `#<hex>` format e.g. `#AB1325`."
                    ))
                )
        else:
            # TODO: Could use a standardised spectrum
            # And use the required value to select a colour
            colour = discord.Colour.random()
        return colour

    requires: TextInput = TextInput(
        label='REQUIRES_PLACEHOLDER',
        max_length=9,
        required=True,
    )

    def requires_setup(self):
        if self.rank_type is RankType.VOICE:
            self.requires.label = self.bot.translator.t(_p(
                'ui:rank_editor|type:voice|input:requires|label',
                "Required Voice Hours"
            ))
            self.requires.placholder = self.bot.translator.t(_p(
                'ui:rank_editor|type:voice|input:requires|placeholder',
                "Number of voice hours before awarding this rank"
            ))
        elif self.rank_type is RankType.XP:
            self.requires.label = self.bot.translator.t(_p(
                'ui:rank_editor|type:xp|input:requires|label',
                "Required XP"
            ))
            self.requires.placholder = self.bot.translator.t(_p(
                'ui:rank_editor|type:xp|input:requires|placeholder',
                "Amount of XP needed before obtaining this rank"
            ))
        elif self.rank_type is RankType.MESSAGE:
            self.requires.label = self.bot.translator.t(_p(
                'ui:rank_editor|type:message|input:requires|label',
                "Required Message Count"
            ))
            self.requires.placholder = self.bot.translator.t(_p(
                'ui:rank_editor|type:message|input:requires|placeholder',
                "Number of messages needed before awarding rank"
            ))

    def requires_parse(self) -> int:
        t = self.bot.translator.t
        value = self.requires.value
        # TODO: Bound checking and errors for each type
        if self.rank_type is RankType.VOICE:
            if value.isdigit():
                data = int(value) * 3600
            else:
                data = parse_duration(self.requires.value)
                if not data:
                    raise UserInputError(
                        _msg=t(_p(
                            'ui:rank_editor|type:voice|input:requires|error:parse',
                            "`requires`: Could not parse provided minimum time! Please write a number of hours."
                        ))
                    )
        elif self.rank_type is RankType.MESSAGE:
            value = value.lower().strip(' messages')
            if value.isdigit():
                data = int(value)
            else:
                raise UserInputError(
                    _msg=t(_p(
                        'ui:rank_editor|type:message|input:requires|error:parse',
                        "`requires`: Could not parse provided minimum message count! Please enter an integer."
                    ))
                )
        elif self.rank_type is RankType.XP:
            value = value.lower().strip(' xps')
            if value.isdigit():
                data = int(value)
            else:
                raise UserInputError(
                    _msg=t(_p(
                        'ui:rank_editor|type:xp|input:requires|error:parse',
                        "`requires`: Could not parse provided minimum XP! Please enter an integer."
                    ))
                )
        return data

    reward: TextInput = TextInput(
        label='REWARD_PLACEHOLDER',
        max_length=9,
        required=False
    )

    def reward_setup(self):
        self.reward.label = self.bot.translator.t(_p(
            'ui:rank_editor|input:reward|label',
            "LionCoins awarded upon achieving this rank"
        ))
        self.reward.placeholder = self.bot.translator.t(_p(
            'ui:rank_editor|input:reward|placeholder',
            "LionCoins awarded upon achieving this rank"
        ))

    def reward_parse(self) -> int:
        t = self.bot.translator.t
        value = self.reward.value
        if not value:
            # Empty value
            data = 0
        elif value.isdigit():
            data = int(value)
        else:
            raise UserInputError(
                _msg=t(_p(
                    'ui:rank_editor|input:reward|error:parse',
                    '`reward`: Please enter an integer number of LionCoins.'
                ))
            )
        return data

    message: TextInput = TextInput(
        label='MESSAGE_PLACEHOLDER',
        style=TextStyle.long,
        max_length=1024,
        required=True
    )

    def message_setup(self):
        t = self.bot.translator.t
        self.message.label = t(_p(
            'ui:rank_editor|input:message|label',
            "Rank Message"
        ))
        self.message.placeholder = t(_p(
            'ui:rank_editor|input:message|placeholder',
            "Congratulatory message sent to the user upon achieving this rank."
        ))
        if self.rank_type is RankType.VOICE:
            # TRANSLATOR NOTE: Don't change the keys here, they will be automatically replaced by the localised key
            msg_default = t(_p(
                'ui:rank_editor|input:message|default|type:voice',
                "Congratulations {user_mention}!\n"
                "For working hard for **{requires}**, you have achieved the rank of "
                "**{role_name}** in **{guild_name}**! Keep up the good work."
            ))
        elif self.rank_type is RankType.XP:
            # TRANSLATOR NOTE: Don't change the keys here, they will be automatically replaced by the localised key
            msg_default = t(_p(
                'ui:rank_editor|input:message|default|type:xp',
                (
                    "Congratulations {user_mention}!\n"
                    "For earning **{requires}**, you have achieved the guild rank of "
                    "**{role_name}** in **{guild_name}**!"
                )
            ))
        elif self.rank_type is RankType.MESSAGE:
            # TRANSLATOR NOTE: Don't change the keys here, they will be automatically replaced by the localised key
            msg_default = t(_p(
                'ui:rank_editor|input:message|default|type:msg',
                (
                    "Congratulations {user_mention}!\n"
                    "For sending **{requires}**, you have achieved the guild rank of "
                    "**{role_name}** in **{guild_name}**!"
                )
            ))
        # Replace the progam keys in the default message with the correct localised keys.
        replace_map = {pkey: t(lkey) for pkey, lkey in rank_message_keys}
        self.message.default = replace_multiple(msg_default, replace_map)

    def message_parse(self) -> str:
        # Replace the localised keys with programmatic keys
        t = self.bot.translator.t
        replace_map = {t(lkey): pkey for pkey, lkey in rank_message_keys}
        return replace_multiple(self.message.value, replace_map)

    def __init__(self, bot: LionBot, rank_type: RankType, **kwargs):
        self.bot = bot
        self.rank_type = rank_type

        self.message_setup()
        self.reward_setup()
        self.requires_setup()
        self.role_name_setup()
        self.role_colour_setup()

        super().__init__(**kwargs)

    @classmethod
    async def edit_rank(cls, interaction: discord.Interaction,
                        rank_type: RankType,
                        rank: AnyRankData, role: discord.Role,
                        callback=None):
        bot = interaction.client
        self = cls(
            bot,
            rank_type,
            title=bot.translator.t(_p('ui:rank_editor|mode:edit|title', "Rank Editor"))
        )
        self.role_name.default = role.name
        self.role_colour.default = str(role.colour)
        self.requires.default = format_stat_range(rank_type, rank.required, None, short=True)
        self.reward.default = rank.reward
        if rank.message:
            t = bot.translator.t
            replace_map = {pkey: t(lkey) for pkey, lkey in rank_message_keys}
            self.message.default = replace_multiple(rank.message, replace_map)

        @self.submit_callback(timeout=15*60)
        async def _edit_rank_callback(interaction):
            # Parse each field in turn
            # A parse error will raise UserInputError and trigger ModalRetry
            role_name = self.role_name_parse()
            role_colour = self.role_colour_parse()
            requires = self.requires_parse()
            reward = self.reward_parse()
            message = self.message_parse()

            # Once successful, use rank.update() to edit the rank if modified,
            if requires != rank.required or reward != rank.reward or message != rank.message:
                # In the corner-case where the rank has been externally deleted, this will be a no-op
                await rank.update(
                    required=requires,
                    reward=reward,
                    message=message
                )
            self.bot.get_cog('RankCog').flush_guild_ranks(interaction.guild.id)
            # and edit the role with role.edit() if modified.
            if role_name != role.name or role_colour != role.colour:
                await role.edit(name=role_name, colour=role_colour)

            # Respond with an update ack..
            # (Might not be required? Or maybe use ephemeral ack?)
            # Finally, run the provided parent callback if provided
            if callback is not None:
                await callback(rank, interaction)

        # Editor ready, now send
        await interaction.response.send_modal(self)
        return self

    @classmethod
    async def create_rank(cls, interaction: discord.Interaction,
                          rank_type: RankType,
                          guild: discord.Guild, role: Optional[discord.Role] = None,
                          callback=None):
        bot = interaction.client
        self = cls(
            bot,
            rank_type,
            title=bot.translator.t(_p(
                'ui:rank_editor|mode:create|title',
                "Rank Creator"
            ))
        )
        if role is not None:
            self.role_name.default = role.name
            self.role_colour.default = str(role.colour)

        @self.submit_callback(timeout=15*60)
        async def _create_rank_callback(interaction):
            # Parse each field in turn
            # A parse error will raise UserInputError and trigger ModalRetry
            role_name = self.role_name_parse()
            role_colour = self.role_colour_parse()
            requires = self.requires_parse()
            reward = self.reward_parse()
            message = self.message_parse()

            # Create or edit the role
            if role is not None:
                rank_role = role
                # Edit role if properties were updated
                if (role_name != role.name or role_colour != role.colour):
                    await role.edit(name=role_name, colour=role_colour)
            else:
                # Create the role
                rank_role = await guild.create_role(name=role_name, colour=role_colour)
                # TODO: Move role to correct position, based on rank list

            # Create the Rank
            model = rank_model_from_type(rank_type)
            rank = await model.create(
                roleid=rank_role.id,
                guildid=guild.id,
                required=requires,
                reward=reward,
                message=message
            )
            self.bot.get_cog('RankCog').flush_guild_ranks(guild.id)

            if callback is not None:
                await callback(rank, interaction)

        # Editor ready, now send
        await interaction.response.send_modal(self)
        return self

    @error_handler_for(UserInputError)
    async def rerequest(self, interaction: discord.Interaction, error: UserInputError):
        await ModalRetryUI(self, error.msg).respond_to(interaction)
