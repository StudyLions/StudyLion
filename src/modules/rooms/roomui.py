from typing import Optional, TYPE_CHECKING
import asyncio

import discord
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.select import select, UserSelect

from meta import LionBot, conf
# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Import ResponseTimedOut for delete room confirmation flow
from meta.errors import UserInputError, ResponseTimedOut
# --- END AI-MODIFIED ---
from meta.logger import log_wrap
from babel.translator import ctx_locale
from utils.lib import utc_now, MessageArgs, error_embed
# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Import Confirm for delete room confirmation dialog
from utils.ui import MessageUI, input, Confirm
# --- END AI-MODIFIED ---
from core.data import CoreData

from modules.pomodoro.ui import TimerOptionsUI, TimerEditor
from modules.pomodoro.lib import TimerRole
from modules.pomodoro.options import TimerOptions

from . import babel, logger
from .data import RoomData
from .settings import RoomSettings
# --- AI-MODIFIED (2026-03-22) ---
# Purpose: Import dashboard URL for link button in room control panel
from .lib import ROOM_DASHBOARD_URL
# --- END AI-MODIFIED ---

if TYPE_CHECKING:
    from .room import Room


_p = babel._p


class RoomUI(MessageUI):
    """
    View status for and reconfigure a rented room.

    May be used by both owners and members,
    but members will get a simplified UI.
    """

    def __init__(self, bot: LionBot, room: 'Room', **kwargs):
        # --- AI-MODIFIED (2026-03-14) ---
        # Purpose: Set guild locale for room UI so translations work if context is missing
        from babel.translator import ctx_locale
        guild_locale = room.lguild.config.get('guild_locale').value
        if guild_locale:
            ctx_locale.set(guild_locale)
        # --- END AI-MODIFIED ---
        super().__init__(**kwargs)
        self.bot = bot
        self.room = room

    async def owner_ward(self, interaction: discord.Interaction):
        t = self.bot.translator.t
        if not interaction.user.id == self.room.data.ownerid:
            await interaction.response.send_message(
                embed=discord.Embed(
                    colour=discord.Colour.brand_red(),
                    description=t(_p(
                        'ui:room_status|error:owner_required',
                        "You must be the private room owner to do this!"
                    ))
                ),
                ephemeral=True
            )
            return False
        return True

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id not in self.room.members and interaction.user.id != self.room.data.ownerid:
            t = self.bot.translator.t
            await interaction.response.send_message(
                embed=discord.Embed(
                    colour=discord.Colour.brand_red(),
                    description=t(_p(
                        'ui:room_status|error:member_required',
                        "You need to be a member of the private room to do this!"
                    ))
                ),
                ephemeral=True
            )
            return False
        return True

    @button(label='DEPOSIT_PLACEHOLDER', style=ButtonStyle.green, emoji=conf.emojis.coin)
    async def desposit_button(self, press: discord.Interaction, pressed: Button):
        t = self.bot.translator.t

        # Open modal, ask how much they want to deposit
        try:
            submit, response = await input(
                press,
                title=t(_p(
                    'ui:room_status|button:deposit|modal:deposit|title',
                    "Room Deposit"
                )),
                question=t(_p(
                    'ui:room_status|button:deposit|modal:deposit|field:question|label',
                    "How many LionCoins do you want to deposit?"
                )),
                required=True,
                max_length=16
            )
        except asyncio.TimeoutError:
            # Input timed out
            # They probably just closed the dialogue
            # Exit silently
            return

        # Input checking
        response = response.strip()
        if not response.isdigit() or (amount := int(response)) == 0:
            await submit.response.send_message(
                embed=error_embed(
                    t(_p(
                        'ui:room_status|button:deposit|error:invalid_number',
                        "Cannot deposit `{inputted}` coins. Please enter a positive integer."
                    )).format(inputted=response)
                ), ephemeral=True
            )
            return
        await submit.response.defer(thinking=True, ephemeral=True)

        await self._do_deposit(t, press, amount, submit)

        # Post deposit message
        await self.room.notify_deposit(press.user, amount)

        await self.refresh(thinking=submit)

    @log_wrap(isolate=True)
    async def _do_deposit(self, t, press, amount, submit):
        # Start transaction for deposit
        async with self.bot.db.connection() as conn:
            self.bot.db.conn = conn
            async with conn.transaction():
                # Get the lion balance directly
                lion = await self.bot.core.data.Member.fetch(
                    self.room.data.guildid,
                    press.user.id,
                    cached=False
                )
                balance = lion.coins
                if balance < amount:
                    await submit.edit_original_response(
                        embed=error_embed(
                            t(_p(
                                'ui:room_status|button:deposit|error:insufficient_funds',
                                "You cannot deposit {coin}**{amount}**! You only have {coin}**{balance}**."
                            )).format(
                                coin=self.bot.config.emojis.coin,
                                amount=amount,
                                balance=balance
                            )
                        )
                    )
                    return
                # TODO: Economy Transaction
                await lion.update(coins=CoreData.Member.coins - amount)
                await self.room.data.update(coin_balance=RoomData.Room.coin_balance + amount)

    async def desposit_button_refresh(self):
        self.desposit_button.label = self.bot.translator.t(_p(
            'ui:room_status|button:deposit|label',
            "Deposit"
        ))

    @button(label='EDIT_PLACEHOLDER', style=ButtonStyle.blurple)
    async def edit_button(self, press: discord.Interaction, pressed: Button):
        if not await self.owner_ward(press):
            return

    async def edit_button_refresh(self):
        self.edit_button.label = self.bot.translator.t(_p(
            'ui:room_status|button:edit|label',
            "Edit Room"
        ))
        self.edit_button.emoji = self.bot.config.emojis.config

    @button(label='TIMER_PLACEHOLDER', style=ButtonStyle.green)
    async def timer_button(self, press: discord.Interaction, pressed: Button):
        if not await self.owner_ward(press):
            return

        timer = self.room.timer
        if timer is not None:
            await TimerEditor.open_editor(self.bot, press, timer, press.user)
        else:
            # Create a new owned timer
            t = self.bot.translator.t
            settings = [
                TimerOptions.FocusLength,
                TimerOptions.BreakLength,
                TimerOptions.InactivityThreshold,
                TimerOptions.BaseName,
                TimerOptions.ChannelFormat
            ]
            instances = [
                setting(self.room.data.channelid, setting._default) for setting in settings
            ]
            instances[3].data = self.room.data.name
            inputs = [
                instance.input_field for instance in instances
            ]
            modal = TimerEditor(
                *inputs,
                title=t(_p(
                    'ui:room_status|button:timer|modal:add_timer|title',
                    "Create Room Timer"
                ))
            )

            @modal.submit_callback(timeout=10*60)
            async def _create_timer_callback(submit: discord.Interaction):
                try:
                    create_args = {
                        'channelid': self.room.data.channelid,
                        'guildid': self.room.data.guildid,
                        'ownerid': self.room.data.ownerid,
                        'notification_channelid': self.room.data.channelid,
                        'manager_roleid': press.guild.default_role.id,
                    }
                    for instance, field in zip(instances, inputs):
                        try:
                            parsed = await instance.from_string(self.room.data.channelid, field.value)
                        except UserInputError as e:
                            _msg = f"`{instance.display_name}:` {e._msg}"
                            raise UserInputError(_msg, info=e.info, details=e.details)
                        create_args[parsed._column] = parsed._data

                    # Parsing okay, start to create
                    await submit.response.defer(thinking=True)

                    timer_cog = self.bot.get_cog('TimerCog')
                    timer = await timer_cog.create_timer(**create_args)
                    await timer.start()

                    await submit.edit_original_response(
                        content=t(_p(
                            'ui:room_status|button:timer|timer_created',
                            "Timer created successfully! Use {edit_cmd} to configure further."
                        )).format(edit_cmd=self.bot.core.mention_cmd('pomodoro edit'))
                    )
                    await self.refresh()
                except UserInputError:
                    raise
                except Exception:
                    logger.exception(
                        "Unhandled exception occurred while creating timer for private room."
                    )
            await press.response.send_modal(modal)

    async def timer_button_refresh(self):
        t = self.bot.translator.t
        button = self.timer_button
        if self.room.timer is not None:
            button.label = t(_p(
                'ui:room_status|button:timer|label:edit_timer',
                "Edit Timer"
            ))
            button.style = ButtonStyle.blurple
            button.emoji = self.bot.config.emojis.config
        else:
            button.label = t(_p(
                'ui:room_status|button:timer|label:add_timer',
                "Add Timer"
            ))
            button.style = ButtonStyle.green
            button.emoji = self.bot.config.emojis.clock

    @button(emoji=conf.emojis.refresh, style=ButtonStyle.grey)
    async def refresh_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        await self.refresh(thinking=press)

    async def refresh_button_refresh(self):
        pass

    @button(emoji=conf.emojis.cancel, style=ButtonStyle.red)
    async def close_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        await self.quit()

    async def close_button_refresh(self):
        pass

    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Add "Delete Room" button so owners can close their room from the control panel
    @button(label='DELETE_PLACEHOLDER', style=ButtonStyle.red)
    async def delete_room_button(self, press: discord.Interaction, pressed: Button):
        if not await self.owner_ward(press):
            return

        t = self.bot.translator.t
        balance = self.room.data.coin_balance
        coin = conf.emojis.coin

        confirm_msg = t(_p(
            'ui:room_status|button:delete_room|confirm',
            "Are you sure you want to permanently close your private room?\n\n"
            "**This cannot be undone.** The voice channel will be deleted "
            "and all members will lose access.\n\n"
            "Remaining balance: {coin}**{balance}** (will be refunded to you)"
        )).format(coin=coin, balance=balance)

        confirm = Confirm(confirm_msg, press.user.id)
        try:
            result = await confirm.ask(press, ephemeral=True)
        except ResponseTimedOut:
            return

        if not result:
            return

        if balance > 0:
            from core.data import CoreData
            lmember = await self.bot.core.lions.fetch_member(self.room.data.guildid, press.user.id)
            await lmember.data.update(coins=CoreData.Member.coins + balance)

        self.room.lguild.log_event(
            title=t(_p(
                'room|eventlog|event:room_owner_deleted|title',
                "Private Room Closed by Owner"
            )),
            description=t(_p(
                'room|eventlog|event:room_owner_deleted|desc',
                "{owner} closed their private room. {coin}**{balance}** was refunded."
            )).format(
                owner=f"<@{press.user.id}>",
                coin=coin,
                balance=balance,
            ),
            fields=self.room.eventlog_fields()
        )

        await self.room.destroy(reason="Owner deleted room via UI")
        await self.quit()

    async def delete_room_button_refresh(self):
        self.delete_room_button.label = self.bot.translator.t(_p(
            'ui:room_status|button:delete_room|label',
            "Delete Room"
        ))
    # --- END AI-MODIFIED ---

    @select(cls=UserSelect, placeholder="INVITE_PLACEHOLDER", min_values=0, max_values=25)
    async def invite_menu(self, selection: discord.Interaction, selected: UserSelect):
        if not await self.owner_ward(selection):
            return
        t = self.bot.translator.t

        userids = set(user.id for user in selected.values)
        userids.discard(self.room.data.ownerid)
        userids.difference_update(self.room.members)
        if not userids:
            # No new members were given, quietly exit
            await selection.response.defer()
            return

        await selection.response.defer(thinking=True, ephemeral=True)
        # Check cap
        cap = self.room.lguild.config.get(RoomSettings.MemberLimit.setting_id).value
        if len(self.room.members) + len(userids) >= cap:
            await selection.edit_original_response(
                embed=error_embed(
                    t(_p(
                        'ui:room_status|menu:invite|error:too_many_members',
                        "Too many members! "
                        "You are inviting `{count}` new members to your room, "
                        "but you already have `{current}` members! "
                        "The member cap is `{cap}`."
                    )).format(
                        count=len(userids),
                        current=len(self.room.members) + 1,
                        cap=cap
                    )
                )
            )
            return

        # Add the members
        await self.room.add_new_members(userids)

        await self.refresh(thinking=selection)

    async def invite_menu_refresh(self):
        t = self.bot.translator.t
        menu = self.invite_menu
        cap = self.room.lguild.config.get('rooms_slots').value
        if len(self.room.members) >= cap:
            menu.disabled = True
            menu.placeholder = t(_p(
                'ui:room_status|menu:invite_menu|placeholder:capped',
                "Room member cap reached!"
            ))
        else:
            menu.disabled = False
            menu.placeholder = t(_p(
                'ui:room_status|menu:invite_menu|placeholder:notcapped',
                "Add Members"
            ))

    @select(cls=UserSelect, placeholder='KICK_MENU_PLACEHOLDER')
    async def kick_menu(self, selection: discord.Interaction, selected: UserSelect):
        if not await self.owner_ward(selection):
            return

        userids = set(user.id for user in selected.values)
        userids.intersection_update(self.room.members)
        if not userids:
            # No selected users are actually members of the room
            await selection.response.defer()
            return

        await selection.response.defer(thinking=True, ephemeral=True)

        await self.room.rm_members(userids)
        await self.refresh(thinking=selection)

    async def kick_menu_refresh(self):
        self.kick_menu.placeholder = self.bot.translator.t(_p(
            'ui:room_status|menu:kick_menu|placeholder',
            "Remove Members"
        ))

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        title = t(_p(
            'ui:room_status|embed|title',
            "Room Control Panel"
        ))
        embed = discord.Embed(
            title=title,
            colour=discord.Colour.orange(),
        )

        embed.add_field(
            name=t(_p('ui:room_status|embed|field:channel|name', "Channel")),
            value=self.room.channel.mention
        )

        embed.add_field(
            name=t(_p('ui:room_status|embed|field:owner|name', "Owner")),
            value=f"<@{self.room.data.ownerid}>"
        )

        embed.add_field(
            name=t(_p('ui:room_status|embed|field:created|name', "Created At")),
            value=f"<t:{int(self.room.data.created_at.timestamp())}>"
        )

        balance = self.room.data.coin_balance
        rent = self.room.rent
        next_tick = f"<t:{int(self.room.next_tick.timestamp())}:R>"
        if self.room.expiring:
            bank_value = t(_p(
                'ui:room_status|embed|field:bank|value:expiring',
                "**Warning:** Insufficient room balance to pay next rent ({coin} **{rent}**).\n"
                "The room will expire {expiry}.\nUse {room_deposit_cmd} to increase balance."
            )).format(
                coin=conf.emojis.coin,
                amount=balance,
                rent=rent,
                expiry=next_tick,
                room_deposit_cmd=self.bot.core.mention_cmd('room deposit')
            )
        else:
            bank_value = t(_p(
                'ui:room_status|embed|field:bank|value:notexpiring',
                "Next rent due {time} (- {coin}**{rent}**)"
            )).format(
                coin=conf.emojis.coin,
                amount=balance,
                rent=rent,
                time=next_tick
            )

        embed.add_field(
            name=t(_p('ui:room_status|embed|field:bank|name', "Room Balance: {coin}**{amount}**")).format(
                coin=self.bot.config.emojis.coin,
                amount=balance
            ),
            value=bank_value,
            inline=False
        )

        member_cap = self.room.lguild.config.get('rooms_slots').value
        embed.add_field(
            name=t(_p(
                'ui:room_status|embed|field:members|name',
                "Members ({count}/{cap})"
            )).format(count=len(self.room.members) + 1, cap=member_cap),
            value=', '.join(f"<@{userid}>" for userid in (self.room.data.ownerid, *self.room.members))
        )

        return MessageArgs(embed=embed)

    async def refresh_layout(self):
        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Add "Dashboard" link button to room control panel layout
        dashboard_link = Button(
            style=ButtonStyle.link,
            url=ROOM_DASHBOARD_URL,
            label="Dashboard",
            emoji="\U0001F4CA"
        )
        # --- END AI-MODIFIED ---
        if self._callerid == self.room.data.ownerid:
            # If the owner called, show full config UI
            # --- AI-MODIFIED (2026-04-01) ---
            # Purpose: Add delete_room_button refresh to owner layout
            # --- Original code (commented out for rollback) ---
            # await asyncio.gather(
            #     self.desposit_button_refresh(),
            #     # self.edit_button_refresh(),
            #     self.refresh_button_refresh(),
            #     self.close_button_refresh(),
            #     self.timer_button_refresh(),
            #     self.invite_menu_refresh(),
            #     self.kick_menu_refresh()
            # )
            # --- End original code ---
            await asyncio.gather(
                self.desposit_button_refresh(),
                self.refresh_button_refresh(),
                self.close_button_refresh(),
                self.timer_button_refresh(),
                self.delete_room_button_refresh(),
                self.invite_menu_refresh(),
                self.kick_menu_refresh()
            )
            # --- END AI-MODIFIED ---
            # --- AI-MODIFIED (2026-04-01) ---
            # Purpose: Include delete_room_button and dashboard link in owner layout
            # --- Original code (commented out for rollback) ---
            # self.set_layout(
            #     (self.desposit_button, self.timer_button, dashboard_link, self.refresh_button, self.close_button),
            #     (self.invite_menu, ),
            #     (self.kick_menu, )
            # )
            # --- End original code ---
            self.set_layout(
                (self.desposit_button, self.timer_button, dashboard_link, self.refresh_button, self.close_button),
                (self.delete_room_button,),
                (self.invite_menu, ),
                (self.kick_menu, )
            )
            # --- END AI-MODIFIED ---
        else:
            # Just show deposit button
            await asyncio.gather(
                self.desposit_button_refresh(),
                self.refresh_button_refresh(),
                self.close_button_refresh(),
            )
            # --- AI-MODIFIED (2026-03-22) ---
            # Purpose: Include dashboard link button in member layout
            # --- Original code (commented out for rollback) ---
            # self.set_layout(
            #     (self.desposit_button, self.refresh_button, self.close_button),
            # )
            # --- End original code ---
            self.set_layout(
                (self.desposit_button, dashboard_link, self.refresh_button, self.close_button),
            )
            # --- END AI-MODIFIED ---

    async def reload(self):
        """
        No need to reload-data, as we use the room as source of truth.
        """
        ...
