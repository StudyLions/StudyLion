from typing import Optional
import asyncio

import discord
from discord.ui.select import select, RoleSelect
from discord.ui.button import button, Button, ButtonStyle

from meta import conf, LionBot
from core.data import RankType
from wards import equippable_role

from utils.ui import MessageUI, AButton, AsComponents
from utils.lib import MessageArgs, replace_multiple
from babel.translator import ctx_translator

from .. import babel, logger
from ..data import AnyRankData
from ..utils import format_stat_range, rank_message_keys
from .editor import RankEditor

_p = babel._p


class RankPreviewUI(MessageUI):
    """
    Preview and edit a single guild rank.

    This UI primarily serves as a platform for deleting the rank and changing the underlying role.
    """
    def __init__(self, bot: LionBot,
                 guild: discord.Guild,
                 rank_type: RankType, rank: AnyRankData,
                 parent: Optional[MessageUI] = None,
                 **kwargs):
        super().__init__(**kwargs)

        self.bot = bot
        self.guild = guild
        self.guildid = guild.id

        self.rank_type = rank_type
        self.rank = rank

        self.parent = parent

    # ----- UI API -----

    # ----- UI Components -----
    @button(emoji=conf.emojis.cancel, style=ButtonStyle.red)
    async def quit_button(self, press: discord.Interaction, pressed: Button):
        """
        Quit the UI.
        """
        await press.response.defer()
        await self.quit()

    async def quit_button_refresh(self):
        pass

    @button(label="EDIT_PLACEHOLDER", style=ButtonStyle.blurple)
    async def edit_button(self, press: discord.Interaction, pressed: Button):
        """
        Open the rank editor for the underlying rank.

        Silent callback, just reload the UI.
        """
        t = self.bot.translator.t
        role = self.guild.get_role(self.rank.roleid)

        error = None
        if role is None:
            # Role no longer exists, prompt to select a new role
            error = t(_p(
                'ui:rank_preview|button:edit|error:role_deleted',
                "The role underlying this rank no longer exists! "
                "Please select a new role from the role menu."
            ))
        elif not role.is_assignable():
            # Role exists but is invalid, prompt to select a new role
            error = t(_p(
                'ui:rank_preview|button:edit|error:role_not_assignable',
                "I do not have permission to edit the underlying role! "
                "Please select a new role from the role menu, "
                "or ensure my top role is above the selected role."
            ))

        if error is not None:
            embed = discord.Embed(
                title=t(_p(
                    'ui:rank_preview|button:edit|error|title',
                    "Failed to edit rank!"
                )),
                description=error,
                colour=discord.Colour.brand_red()
            )
            await press.response.send_message(embed=embed)
        else:
            await RankEditor.edit_rank(
                press,
                self.rank_type,
                self.rank,
                role,
                callback=self._editor_callback
            )

    async def edit_button_refresh(self):
        self.edit_button.label = self.bot.translator.t(_p(
            'ui:rank_preview|button:edit|label',
            "Edit"
        ))

    async def _editor_callback(self, rank: AnyRankData, submit: discord.Interaction):
        await submit.response.defer(thinking=False)
        if self.parent is not None:
            asyncio.create_task(self.parent.refresh())
        self.bot.get_cog('RankCog').flush_guild_ranks(self.guild.id)
        await self.refresh()

    @button(label="DELETE_PLACEHOLDER", style=ButtonStyle.red)
    async def delete_button(self, press: discord.Interaction, pressed: Button):
        """
        Delete the current rank, post a deletion message, and quit the UI.

        Also refreshes the parent, if set.
        """
        t = self.bot.translator.t
        await press.response.defer(thinking=True, ephemeral=True)

        roleid = self.rank.roleid
        role = self.guild.get_role(roleid)
        if not (role and self.guild.me.guild_permissions.manage_roles and self.guild.me.top_role > role):
            role = None

        await self.rank.delete()
        self.bot.get_cog('RankCog').flush_guild_ranks(self.guild.id)

        mention = role.mention if role else str(self.rank.roleid)

        if role:
            desc = t(_p(
                'ui:rank_preview|button:delete|response:success|description|with_role',
                "You have deleted the rank {mention}. Press the button below to also delete the role."
            )).format(mention=mention)
        else:
            desc = t(_p(
                'ui:rank_preview|button:delete|response:success|description|no_role',
                "You have deleted the rank {mention}."
            )).format(mention=mention)

        embed = discord.Embed(
            title=t(_p(
                'ui:rank_preview|button:delete|response:success|title',
                "Rank Deleted"
            )),
            description=desc,
            colour=discord.Colour.red()
        )

        if role:
            # Add a micro UI to the response to delete the underlying role
            delete_role_label = t(_p(
                    'ui:rank_preview|button:delete|response:success|button:delete_role|label',
                    "Delete Role"
            ))

            @AButton(label=delete_role_label, style=ButtonStyle.red)
            async def delete_role(_press: discord.Interaction, pressed: Button):
                # Don't need an interaction check here because the message is ephemeral
                rolename = role.name
                try:
                    await role.delete()
                    errored = False
                except discord.HTTPException:
                    errored = True

                if errored:
                    embed.description = t(_p(
                        'ui:rank_preview|button:delete|response:success|button:delete_role|response:errored|desc',
                        "You have deleted the rank **{name}**! "
                        "Could not delete the role due to an unknown error."
                    )).format(name=rolename)
                else:
                    embed.description = t(_p(
                        'ui:rank_preview|button:delete|response:success|button:delete_role|response:success|desc',
                        "You have deleted the rank **{name}** along with the underlying role."
                    )).format(name=rolename)

                await press.edit_original_response(embed=embed, view=None)

            await press.edit_original_response(embed=embed, view=AsComponents(delete_role))
        else:
            # Just send the deletion embed
            await press.edit_original_response(embed=embed)

        if self.parent is not None and not self.parent.is_finished():
            asyncio.create_task(self.parent.refresh())
        await self.quit()

    async def delete_button_refresh(self):
        self.delete_button.label = self.bot.translator.t(_p(
            'ui:rank_preview|button:delete|label',
            "Delete Rank"
        ))

    @select(cls=RoleSelect, placeholder="NEW_ROLE_MENU", min_values=1, max_values=1)
    async def role_menu(self, selection: discord.Interaction, selected):
        """
        Select a new role for this rank.

        Certain checks are enforced.
        Note this can potentially create two ranks with the same role.
        This will not cause any systemic issues aside from confusion.
        """
        t = self.bot.translator.t
        role: discord.Role = selected.values[0]
        await selection.response.defer(thinking=True, ephemeral=True)

        if role.is_assignable():
            # Update the rank role
            # Generic permission check for the new role
            await equippable_role(self.bot, role, selection.user)

            await self.rank.update(roleid=role.id)
            self.bot.get_cog('RankCog').flush_guild_ranks(self.guild.id)
            if self.parent is not None and not self.parent.is_finished():
                asyncio.create_task(self.parent.refresh())
            await self.refresh(thinking=selection)
        else:
            if role.is_default():
                error = t(_p(
                    'ui:rank_preview|menu:roles|error:not_assignable|suberror:is_default',
                    "The @everyone role cannot be removed, and cannot be a rank!"
                ))
            elif role.managed:
                error = t(_p(
                    'ui:rank_preview|menu:roles|error:not_assignable|suberror:is_managed',
                    "The role is managed by another application or integration, and cannot be a rank!"
                ))
            elif not self.guild.me.guild_permissions.manage_roles:
                error = t(_p(
                    'ui:rank_preview|menu:roles|error:not_assignable|suberror:no_permissions',
                    "I do not have the `MANAGE_ROLES` permission in this server, so I cannot manage ranks!"
                ))
            elif (role >= self.guild.me.top_role):
                error = t(_p(
                    'ui:rank_preview|menu:roles|error:not_assignable|suberror:above_me',
                    "This role is above my top role in the role hierarchy, so I cannot add or remove it!"
                ))
            else:
                # Catch all for other potential issues
                error = t(_p(
                    'ui:rank_preview|menu:roles|error:not_assignable|suberror:other',
                    "I am not able to manage the selected role, so it cannot be a rank!"
                ))

            embed = discord.Embed(
                title=t(_p(
                    'ui:rank_preview|menu:roles|error:not_assignable|title',
                    "Could not update rank!"
                )),
                description=error,
                colour=discord.Colour.brand_red()
            )
            await selection.edit_original_response(embed=embed)

    async def role_menu_refresh(self):
        self.role_menu.placeholder = self.bot.translator.t(_p(
            'ui:rank_preview|menu:roles|placeholder',
            "Update Rank Role"
        ))

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        # TODO: Localise
        t = self.bot.translator.t
        rank = self.rank

        embed = discord.Embed(
            title=t(_p(
                'ui:rank_preview|embed|title',
                "Rank Information"
            )),
            colour=discord.Colour.orange()
        )
        embed.add_field(
            name=t(_p(
                'ui:rank_preview|embed|field:role|name',
                "Role"
            )),
            value=f"<@&{rank.roleid}>"
        )
        embed.add_field(
            name=t(_p(
                'ui:rank_preview|embed|field:required|name',
                "Required"
            )),
            value=format_stat_range(self.rank_type, rank.required, short=False)
        )
        embed.add_field(
            name=t(_p(
                'ui:rank_preview|embed|field:reward|name',
                "Reward"
            )),
            value=f"{conf.emojis.coin}**{rank.reward}**"
        )
        replace_map = {pkey: t(lkey) for pkey, lkey in rank_message_keys}
        message = replace_multiple(rank.message, replace_map)
        embed.add_field(
            name=t(_p(
                'ui:rank_preview|embed|field:message',
                "Congratulatory Message"
            )),
            value=f"```{message}```"
        )
        return MessageArgs(embed=embed)

    async def refresh_layout(self):
        await asyncio.gather(
            self.role_menu_refresh(),
            self.edit_button_refresh(),
            self.delete_button_refresh(),
            self.quit_button_refresh()
        )
        self.set_layout(
            (self.role_menu,),
            (self.edit_button, self.delete_button, self.quit_button,)
        )

    async def reload(self):
        """
        Refresh the stored rank data.

        Generally not required since RankData uses a Registry pattern.
        """
        ...
