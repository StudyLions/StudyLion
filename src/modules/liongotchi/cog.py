# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-15
# Purpose: LionGotchi Discord cog - single /pet command with
#          full button-based navigation (no other slash commands)
# ============================================================
import logging
import asyncio
import traceback
import time as _time
import math
from datetime import datetime, timezone
from io import BytesIO
import random

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds

# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Add Babel localization for text branding support
# LazyStr (from babel._p) is not JSON-serializable; discord.py's
# json.dumps crashes when LazyStr appears in button labels or message
# payloads.  Resolve to plain str immediately so every call site is safe.
from . import babel
def _p(context, message):
    return str(babel._p(context, message))
# --- END AI-MODIFIED ---

from meta import LionBot, LionCog, LionContext, conf, WEBSITE_URL
from .data import (
    LionGotchiData, LGExpression, LGEquipmentSlot, LGItemSource,
    LGGoldTransactionType
)
# --- AI-MODIFIED (2026-03-15) ---
# Purpose: Import fullscreen render functions for toggle feature
from .renderer import PetState, render_gameboy_frame, render_fullscreen_frame, render_action_frame
from .farm_renderer import FarmState, render_farm_frame, render_farm_fullscreen
# --- END AI-MODIFIED ---
# --- AI-MODIFIED (2026-03-20) ---
# Purpose: Import onboarding GIF renderer for visual tutorial and first encounter
from .onboarding_renderer import OnboardingGIFs
# --- END AI-MODIFIED ---
# --- AI-MODIFIED (2026-03-19) ---
# Purpose: Import mood system functions alongside existing gameplay imports
from .gameplay import (
    process_voice_activity, process_text_activity,
    process_farm_growth, process_family_farm_growth,
    attempt_enhance, calc_equipment_bonus,
    try_item_drop, ITEM_DROP_CHANCE_TEXT, ITEM_DROP_CHANCE_HARVEST,
    MAX_ENHANCEMENT_BY_RARITY, ENHANCEMENT_GOLD_BONUS, calc_level_penalty,
    DAILY_GOLD_CAP, DAILY_XP_CAP, DAILY_DROP_CAP, LG_MSG_COOLDOWN_SECONDS,
    LG_TEXT_SESSION_MSG_CAP,
    calc_mood, MOOD_MULTIPLIERS, MOOD_LABELS, MOOD_EMOJI,
    award_family_xp, family_level_from_xp,
)
# --- END AI-MODIFIED ---

logger = logging.getLogger(__name__)

# --- AI-REPLACED (2026-03-19) ---
# Reason: Stat redesign -- shorter cooldowns, slower decay, consistent sleep cooldown
# What the new code does better: 2-min cooldowns feel responsive; 6h decay is forgiving
#   enough to not punish users now that mood affects earnings
# --- Original code (commented out for rollback) ---
# FEED_COOLDOWN_SECONDS = 300
# BATHE_COOLDOWN_SECONDS = 300
# NEEDS_DECAY_INTERVAL_HOURS = 4
# NEEDS_DECAY_AMOUNT = 1
# --- End original code ---
# --- AI-REPLACED (2026-05-15) ---
# Reason: User report -- stats deplete too fast after long absences ("leveled up, all stats gone"),
#   and 4 clicks per stat to refill is painful. Slow decay to 1/24h (8 days to empty), cap
#   accumulated decay per wake at 4 to prevent shock drops, drop cooldowns since one click now
#   fills the stat to max anyway.
# What the new code does better: forgiving for casual users, no "I came back and everything is 0"
# --- Original code (commented out for rollback) ---
# FEED_COOLDOWN_SECONDS = 120
# BATHE_COOLDOWN_SECONDS = 120
# SLEEP_COOLDOWN_SECONDS = 120
# NEEDS_DECAY_INTERVAL_HOURS = 6
# NEEDS_DECAY_AMOUNT = 1
# --- End original code ---
FEED_COOLDOWN_SECONDS = 0
BATHE_COOLDOWN_SECONDS = 0
SLEEP_COOLDOWN_SECONDS = 0
NEEDS_DECAY_INTERVAL_HOURS = 24
NEEDS_DECAY_AMOUNT = 1
MAX_DECAY_PER_WAKE = 4
# --- END AI-REPLACED ---
# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Reduce pet warning spam -- once per week instead of every 4 hours
# --- Original code (commented out for rollback) ---
# PET_WARNING_COOLDOWN_SECONDS = 4 * 3600
# --- End original code ---
PET_WARNING_COOLDOWN_SECONDS = 7 * 24 * 3600
# --- END AI-MODIFIED ---
# --- END AI-REPLACED ---

# --- AI-MODIFIED (2026-03-16) ---
# Purpose: Helper to safely resolve LionGotchi custom emojis with Unicode fallback.
#          Returns the custom emoji string for embed text, or the PartialEmoji
#          object for button emojis. Falls back to Unicode if the emoji ID is
#          not yet configured (placeholder 0).
def _lg_emoji(name, fallback=''):
    """Get a LionGotchi custom emoji string for use in embed text."""
    try:
        e = getattr(conf.emojis, name, None)
        if e and getattr(e, 'id', None):
            return str(e)
    except Exception:
        pass
    return fallback


def _lg_partial(name, fallback=''):
    """Get a LionGotchi PartialEmoji for use as a button emoji."""
    try:
        e = getattr(conf.emojis, name, None)
        if e and getattr(e, 'id', None):
            return e
    except Exception:
        pass
    return fallback
# --- END AI-MODIFIED ---


async def _db_fetch(bot, query: str, *args):
    """Execute a SELECT query and return rows as list of dicts."""
    async with bot.db.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, list(args) if args else None)
            return await cur.fetchall()


async def _db_exec(bot, query: str, *args):
    """Execute a non-SELECT query (INSERT/UPDATE/DELETE)."""
    async with bot.db.connection() as conn:
        await conn.execute(query, list(args) if args else None)


# ============================================================
# Onboarding Tutorial (shown to new users on first /pet)
# ============================================================
# --- AI-MODIFIED (2026-03-16) ---
# Purpose: Multi-page onboarding tutorial for first-time LionGotchi users

# --- AI-REPLACED (2026-03-20) ---
# Reason: Condensed 7-page text-only tutorial to 4 visual pages with GIF previews
# What the new code does better: Fewer pages, animated GIF showcase for each feature,
#   punchier copy that shows rather than tells
# --- Original code (commented out for rollback) ---
# ONBOARDING_PAGES = [
#     {'title': 'Welcome to LionGotchi!', ..., 'footer': 'Page 1/7'},
#     {'title': 'Taking Care of Your Pet', ..., 'footer': 'Page 2/7'},
#     {'title': 'Equipment & Drops', ..., 'footer': 'Page 3/7'},
#     {'title': 'Your Farm', ..., 'footer': 'Page 4/7'},
#     {'title': 'Room & Marketplace', ..., 'footer': 'Page 5/7'},
#     {'title': 'LionGems & LionHeart', ..., 'footer': 'Page 6/7'},
#     {'title': 'Name Your Pet & Get Started!', ..., 'footer': 'Page 7/7'},
# ]
# --- End original code ---
ONBOARDING_PAGES = [
    {
        'title': _p('onboard:page1|title', '\U0001F981 Welcome to LionGotchi!'),
        'color': 0xffd700,
        'gif_key': 'welcome',
        'description': _p(
            'onboard:page1|desc',
            (
                "**LionGotchi** is your virtual pet that grows alongside "
                "your productivity journey!\n\n"
                "\U0001F43E **Adopt a pet** \u2014 name it, care for it, watch it level up\n"
                "\u2694\uFE0F **Earn equipment** \u2014 gear drops while you're productive\n"
                "\U0001F331 **Grow a farm** \u2014 plant seeds, harvest rare crops\n"
                "\U0001F3E0 **Customize a room** \u2014 furniture, themes, and trophies\n"
                "\U0001F4B0 **Trade with others** \u2014 buy and sell on the marketplace\n\n"
                "The more productive you are, the more you earn. Let's show you!"
            ),
        ),
        'footer': _p('onboard:page1|footer', 'Page 1/4'),
    },
    {
        'title': _p('onboard:page2|title', '\U0001F43E Pet Care & Equipment'),
        'color': 0xff6b6b,
        'gif_key': 'equipment',
        'description': _p(
            'onboard:page2|desc',
            (
                "**Care for your pet** \u2014 it has three needs that decay over time:\n"
                "\U0001F356 Food \u2022 \U0001F9FC Bath \u2022 \U0001F4A4 Sleep\n"
                "Happy pets earn **more gold and XP** from your productive sessions!\n\n"
                "**Equipment drops** as you're productive:\n"
                "\u26AA Common \u2022 \U0001F7E2 Uncommon \u2022 \U0001F535 Rare \u2022 "
                "\U0001F7E3 Epic \u2022 \U0001F7E0 Legendary \u2022 \U0001F534 Mythical\n\n"
                "\U0001F6E1\uFE0F Equip gear to **head, face, body, back, and feet**\n"
                "\U0001F4DC Use scrolls to **enhance** equipment for bigger bonuses\n"
                f"\u2022 Manage gear: **{WEBSITE_URL}/pet/inventory**"
            ),
        ),
        'footer': _p('onboard:page2|footer', 'Page 2/4'),
    },
    {
        'title': _p('onboard:page3|title', '\U0001F331 Farm & Marketplace'),
        'color': 0x2ecc71,
        'gif_key': 'farm',
        'description': _p(
            'onboard:page3|desc',
            (
                "**Your Farm** \u2014 15 plots to grow crops!\n"
                "\U0001FAB4 Plant seeds \u2022 \U0001F4A7 Water daily \u2022 "
                "\U0001F33E Harvest for gold and bonus drops\n"
                "Your farm grows automatically as you're productive.\n\n"
                "**Marketplace** \u2014 trade with the whole community!\n"
                "List equipment and scrolls for sale, browse rare items, "
                "and build your collection.\n\n"
                "**LionGems** \u2014 earn free gems by voting on top.gg!\n"
                f"\u2022 Farm: **{WEBSITE_URL}/pet/farm**\n"
                f"\u2022 Market: **{WEBSITE_URL}/pet/marketplace**"
            ),
        ),
        'footer': _p('onboard:page3|footer', 'Page 3/4'),
    },
    {
        'title': _p('onboard:page4|title', '\U0001F680 Name Your Pet & Get Started!'),
        'color': 0xffd700,
        'gif_key': None,
        'description': _p(
            'onboard:page4|desc',
            (
                "You're ready! Tap **Adopt!** to name your pet and begin.\n\n"
                "**Quick recap:**\n"
                "\u2022 `/pet` \u2014 Check on your pet anytime\n"
                "\u2022 Stay productive \u2014 Equipment drops automatically\n"
                f"\u2022 **{WEBSITE_URL}/pet** \u2014 Your hub for farming, "
                "room design, and the marketplace\n"
                "\u2022 Vote on **top.gg** \u2014 Free gems every 12 hours\n\n"
                "Your pet's name can be changed later, so don't worry "
                "about picking the perfect one right now.\n\n"
                "Good luck, and stay productive! \U0001F981"
            ),
        ),
        'footer': _p('onboard:page4|footer', 'Page 4/4'),
    },
]
# --- END AI-REPLACED ---


# --- AI-REPLACED (2026-03-20) ---
# Reason: Visual onboarding with GIF previews, condensed to 4 pages, removed Skip Tutorial
# What the new code does better: Each page has an animated GIF showing the feature;
#   Adopt button always green and available; cleaner 4-page flow
# --- Original code (commented out for rollback) ---
# class OnboardingView(discord.ui.View):
#     """7-page text-only paginated onboarding."""
#     def __init__(self, cog, user_id):
#         self.page = 0
#         self.add_item(Button(label='Learn More', url=...))
#     def _build_embed(self): ...
#     def _update_buttons(self): ...
#     back_btn, next_btn, adopt_btn, skip_btn decorators
# --- End original code ---
class OnboardingView(discord.ui.View):
    """Visual paginated onboarding tutorial with GIF previews for first-time /pet users."""

    def __init__(self, cog: 'LionGotchiCog', user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.page = 0
        self._onboarding_gifs: OnboardingGIFs = getattr(cog, '_onboarding_gifs', None)
        self.add_item(discord.ui.Button(
            label=_p('ui:onboard|button:learn_more|label', 'Learn More'), emoji='\U0001F4D6',
            style=discord.ButtonStyle.link,
            url=f'{WEBSITE_URL}/pet', row=1
        ))
        self._update_buttons()

    async def _build_embed_and_file(self) -> tuple[discord.Embed, discord.File | None]:
        data = ONBOARDING_PAGES[self.page]
        embed = discord.Embed(
            title=data['title'],
            description=data['description'],
            color=data['color']
        )
        embed.set_footer(text=f"{data['footer']}  \u2022  {WEBSITE_URL}/pet")
        gif_file = None
        gif_key = data.get('gif_key')
        if gif_key and self._onboarding_gifs:
            try:
                gif_bytes = await self._onboarding_gifs.get(gif_key)
                gif_file = discord.File(BytesIO(gif_bytes), filename=f"{gif_key}.gif")
                embed.set_image(url=f"attachment://{gif_key}.gif")
            except Exception:
                logger.debug(f"Failed to load onboarding GIF: {gif_key}")
        return embed, gif_file

    def _update_buttons(self):
        self.back_btn.disabled = (self.page == 0)
        is_last = (self.page == len(ONBOARDING_PAGES) - 1)
        self.next_btn.disabled = is_last
        self.adopt_btn.style = discord.ButtonStyle.green

    @discord.ui.button(label=_p('ui:onboard|button:back|label', 'Back'), emoji='\u25C0', style=discord.ButtonStyle.grey, row=0)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return
        if self.page > 0:
            self.page -= 1
            self._update_buttons()
            embed, gif_file = await self._build_embed_and_file()
            attachments = [gif_file] if gif_file else []
            await interaction.response.edit_message(
                embed=embed, view=self, attachments=attachments
            )

    @discord.ui.button(label=_p('ui:onboard|button:next|label', 'Next'), emoji='\u25B6', style=discord.ButtonStyle.blurple, row=0)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return
        if self.page < len(ONBOARDING_PAGES) - 1:
            self.page += 1
            self._update_buttons()
            embed, gif_file = await self._build_embed_and_file()
            attachments = [gif_file] if gif_file else []
            await interaction.response.edit_message(
                embed=embed, view=self, attachments=attachments
            )

    @discord.ui.button(label=_p('ui:onboard|button:adopt|label', 'Adopt!'), emoji='\U0001F43E', style=discord.ButtonStyle.green, row=0)
    async def adopt_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return
        self.stop()
        await interaction.response.send_modal(PetAdoptModal(self.cog))
# --- END AI-REPLACED ---

class PetAdoptModal(discord.ui.Modal, title=_p('modal:adopt|title', 'Name Your LionGotchi!')):
    """Modal shown during onboarding to let users choose a name before pet creation."""

    name_input = discord.ui.TextInput(
        label=_p('modal:adopt|field:name|label', 'Pet Name'),
        placeholder=_p('modal:adopt|field:name|placeholder', 'Choose a name (max 12 chars)'),
        default="Leo",
        max_length=12,
        required=True,
    )

    def __init__(self, cog: 'LionGotchiCog'):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        name = self.name_input.value.strip()[:12] or "Leo"
        pet = await self.cog._get_or_create_pet(interaction.user.id)
        if pet is None:
            await interaction.response.send_message(
                _p('error:adopt|failed', 'Something went wrong creating your pet. Try `/pet` again!'),
                ephemeral=True
            )
            return
        await _db_exec(self.cog.bot,
            "UPDATE lg_pets SET pet_name = %s WHERE userid = %s",
            name, interaction.user.id
        )
        await self.cog._show_pet(interaction, edit=False)

# --- END AI-MODIFIED ---


# ============================================================
# Pet Name Modal (replaces /petname)
# ============================================================
class PetNameModal(discord.ui.Modal, title=_p('modal:rename|title', 'Rename Your Pet')):
    name_input = discord.ui.TextInput(
        label=_p('modal:rename|field:name|label', 'New Name'),
        placeholder=_p('modal:rename|field:name|placeholder', 'Enter a name (max 12 chars)'),
        max_length=12,
        required=True,
    )

    def __init__(self, cog: 'LionGotchiCog'):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        name = self.name_input.value.strip()[:12]
        if not name:
            await interaction.response.send_message(
                _p('error:rename|invalid_name', 'Invalid name!'), ephemeral=True
            )
            return
        await _db_exec(self.cog.bot,
            "UPDATE lg_pets SET pet_name = %s WHERE userid = %s",
            name, interaction.user.id
        )
        await self.cog._show_pet(interaction, edit=True)


# ============================================================
# Sub-Views (Inventory, Shop, Room, Skin)
# ============================================================
# --- AI-MODIFIED (2026-03-16) ---
# Purpose: InventoryView -- Materials tab removed (materials no longer exist)
#          filter tabs are now Equipment/Scrolls only

class InventoryView(discord.ui.View):
    FILTER_EQUIPMENT = 'equipment'
    FILTER_SCROLLS = 'scrolls'

    def __init__(self, cog: 'LionGotchiCog', user_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.page = 0
        self.items = []
        self.page_size = 8
        self.active_filter = self.FILTER_EQUIPMENT

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def load_items(self):
        if self.active_filter == self.FILTER_SCROLLS:
            self.items = await _db_fetch(self.cog.bot,
                """SELECT ui.inventoryid, ui.itemid, ui.quantity, ui.enhancement_level,
                          i.name, i.category, i.rarity, i.slot, i.asset_path,
                          false AS equipped, false AS is_cosmetic
                   FROM lg_user_inventory ui
                   JOIN lg_items i ON ui.itemid = i.itemid
                   WHERE ui.userid = %s AND i.category = 'SCROLL' AND ui.quantity > 0
                   ORDER BY i.rarity, i.name""",
                self.user_id
            ) or []
        else:
            # --- AI-MODIFIED (2026-04-24) ---
            # Purpose: Also LEFT JOIN lg_pet_cosmetics so each row knows whether
            # the item is currently set as a cosmetic. Drives the cosmetic
            # toggle button label (Set/Remove) on row 2 of the view.
            rows = await _db_fetch(self.cog.bot,
                """SELECT ui.inventoryid, ui.itemid, ui.quantity, ui.enhancement_level,
                          i.name, i.category, i.rarity, i.slot, i.asset_path,
                          e.slot IS NOT NULL AS equipped,
                          c.slot IS NOT NULL AS is_cosmetic
                   FROM lg_user_inventory ui
                   JOIN lg_items i ON ui.itemid = i.itemid
                   LEFT JOIN lg_pet_equipment e ON e.userid = ui.userid AND e.itemid = i.itemid
                   LEFT JOIN lg_pet_cosmetics c ON c.userid = ui.userid AND c.itemid = i.itemid
                   WHERE ui.userid = %s
                     AND i.category NOT IN ('MATERIAL', 'SCROLL', 'CONSUMABLE')
                   ORDER BY ui.enhancement_level DESC, i.rarity DESC, i.category, i.name""",
                self.user_id
            ) or []
            # --- END AI-MODIFIED ---
            seen = set()
            self.items = []
            for r in rows:
                key = (r['itemid'], r.get('enhancement_level', 0))
                if key not in seen:
                    seen.add(key)
                    self.items.append(r)
        # --- AI-MODIFIED (2026-04-24) ---
        # Purpose: Cache the master cosmetics_enabled flag for label decisions
        # in refresh_buttons. Single fetch, refreshed every load_items call so
        # toggling stays in sync.
        try:
            row = await _db_fetch(self.cog.bot,
                "SELECT cosmetics_enabled FROM lg_pets WHERE userid = %s",
                self.user_id)
            if row and row[0].get('cosmetics_enabled') is not None:
                self.cosmetics_enabled = bool(row[0]['cosmetics_enabled'])
            else:
                self.cosmetics_enabled = True
        except Exception:
            self.cosmetics_enabled = True
        # --- END AI-MODIFIED ---

    def make_embed(self) -> discord.Embed:
        filter_labels = {
            self.FILTER_EQUIPMENT: f"\U0001F6E1\uFE0F {_p('ui:inventory|filter:equipment|label', 'Equipment')}",
            self.FILTER_SCROLLS: f"\U0001F4DC {_p('ui:inventory|filter:scrolls|label', 'Scrolls')}",
        }
        embed = discord.Embed(
            title=str(_p('embed:inventory|title', 'Inventory - {filter}')).format(
                filter=str(filter_labels[self.active_filter])),
            color=discord.Color.gold()
        )
        if not self.items:
            if self.active_filter == self.FILTER_SCROLLS:
                embed.description = str(_p(
                    'embed:inventory|desc:empty_scrolls',
                    'No scrolls yet! Keep being productive to earn scroll drops.'))
            else:
                embed.description = str(_p(
                    'embed:inventory|desc:empty_equip',
                    'No equipment yet! Buy from the shop or earn drops from activity.'))
            return embed

        start = self.page * self.page_size
        page_items = self.items[start:start + self.page_size]
        lines = []
        for it in page_items:
            rarity = it['rarity'] if isinstance(it['rarity'], str) else str(it['rarity'])
            if self.active_filter == self.FILTER_SCROLLS:
                qty = it.get('quantity', 1)
                lines.append(f"**{it['name']}** x{qty} ({rarity})")
            else:
                enh = it.get('enhancement_level', 0)
                equipped = " \U0001F6E1\uFE0F" if it['equipped'] else ""
                # --- AI-MODIFIED (2026-04-24) ---
                # Purpose: Sparkle marker indicates an item set as cosmetic
                # overlay. Rendered alongside the equipped shield so a user
                # can see at a glance which items contribute stats vs visuals.
                cos_marker = " \u2728" if it.get('is_cosmetic') else ""
                # --- END AI-MODIFIED ---
                name = f"**{it['name']} +{enh}**" if enh > 0 else f"**{it['name']}**"
                max_enh = MAX_ENHANCEMENT_BY_RARITY.get(rarity, 5)
                enh_info = f" [{enh}/{max_enh}]" if enh > 0 else ""
                slot_label = it['slot'] or it['category']
                lines.append(f"{name} ({rarity}){enh_info}{equipped}{cos_marker}\n  {slot_label}")

        embed.description = "\n".join(lines)
        total_pages = max(1, (len(self.items) + self.page_size - 1) // self.page_size)
        embed.set_footer(text=str(_p(
            'embed:inventory|footer',
            'Page {cur}/{total} | {count} items')).format(
                cur=self.page + 1, total=total_pages, count=len(self.items)))
        return embed

    def refresh_buttons(self):
        self.clear_items()

        # Filter tabs (row 0)
        for filt, label, emoji in [
            (self.FILTER_EQUIPMENT, _p('ui:inventory|filter:equipment|label', 'Equipment'), "\U0001F6E1\uFE0F"),
            (self.FILTER_SCROLLS, _p('ui:inventory|filter:scrolls|label', 'Scrolls'), "\U0001F4DC"),
        ]:
            style = discord.ButtonStyle.blurple if filt == self.active_filter else discord.ButtonStyle.grey
            btn = discord.ui.Button(label=label, emoji=emoji, style=style, row=0)
            btn.callback = self._make_filter_cb(filt)
            self.add_item(btn)

        # Pagination (row 0)
        total_pages = max(1, (len(self.items) + self.page_size - 1) // self.page_size)
        if total_pages > 1:
            prev_btn = discord.ui.Button(
                label=_p('ui:inventory|button:page_prev|label', '<'),
                style=discord.ButtonStyle.grey, row=0, disabled=self.page == 0)
            prev_btn.callback = self.prev_page
            self.add_item(prev_btn)
            next_btn = discord.ui.Button(
                label=_p('ui:inventory|button:page_next|label', '>'),
                style=discord.ButtonStyle.grey, row=0, disabled=self.page >= total_pages - 1)
            next_btn.callback = self.next_page
            self.add_item(next_btn)

        # Item action buttons (row 1-2) -- only for equipment tab
        if self.active_filter == self.FILTER_EQUIPMENT:
            start = self.page * self.page_size
            page_items = self.items[start:start + self.page_size]
            # --- AI-MODIFIED (2026-04-24) ---
            # Purpose: Restrict to first 4 items so we still have room for the
            # parallel cosmetic toggle row (row 2). Discord caps each row at
            # 5 buttons, so equip + cosmetic for 4 items keeps the layout
            # readable.
            for it in page_items[:4]:
            # --- END AI-MODIFIED ---
                if it['equipped']:
                    btn = discord.ui.Button(
                        label=str(_p('ui:inventory|button:unequip|label', 'Unequip {name}')).format(
                            name=it['name'][:12]),
                        style=discord.ButtonStyle.red, row=1)
                    btn.callback = self._make_unequip_cb(it)
                elif it.get('slot'):
                    btn = discord.ui.Button(
                        label=str(_p('ui:inventory|button:equip|label', 'Equip {name}')).format(
                            name=it['name'][:14]),
                        style=discord.ButtonStyle.green, row=1)
                    btn.callback = self._make_equip_cb(it)
                else:
                    continue
                self.add_item(btn)

            # --- AI-GENERATED (2026-04-24) ---
            # Purpose: Cosmetic toggle row -- one button per visible item.
            # Lets users mark an item as the "visual override" for its slot
            # without affecting the stat-bearing equipment row. Items with
            # no slot (e.g. plain materials) are skipped just like equip.
            for it in page_items[:4]:
                if not it.get('slot'):
                    continue
                if it.get('is_cosmetic'):
                    cos_btn = discord.ui.Button(
                        label=str(_p('ui:inventory|button:cosmetic_remove|label',
                                     'Hide cosmetic {name}')).format(name=it['name'][:8]),
                        emoji="\U0001F441",
                        style=discord.ButtonStyle.red, row=2)
                    cos_btn.callback = self._make_unset_cosmetic_cb(it)
                else:
                    cos_btn = discord.ui.Button(
                        label=str(_p('ui:inventory|button:cosmetic_set|label',
                                     'Show {name}')).format(name=it['name'][:10]),
                        emoji="\u2728",
                        style=discord.ButtonStyle.blurple, row=2)
                    cos_btn.callback = self._make_set_cosmetic_cb(it)
                self.add_item(cos_btn)
            # --- END AI-GENERATED ---

        # Enhance button (row 3)
        if self.active_filter == self.FILTER_EQUIPMENT:
            enhance_btn = discord.ui.Button(label=_p('ui:inventory|button:enhance|label', 'Enhance'), emoji="\u2728",
                                             style=discord.ButtonStyle.blurple, row=3)
            enhance_btn.callback = self._go_enhance
            self.add_item(enhance_btn)

            # --- AI-GENERATED (2026-04-24) ---
            # Purpose: Master toggle for the cosmetic overlay. When OFF the
            # renderer ignores all lg_pet_cosmetics rows -- the user sees
            # their "true equipment view" while keeping their picks saved.
            cos_enabled = getattr(self, 'cosmetics_enabled', True)
            toggle_btn = discord.ui.Button(
                label=str(_p('ui:inventory|button:cosmetics_off|label',
                             'Cosmetics: ON')) if cos_enabled
                      else str(_p('ui:inventory|button:cosmetics_on|label',
                                  'Cosmetics: OFF')),
                emoji="\U0001F3AD",
                style=discord.ButtonStyle.green if cos_enabled else discord.ButtonStyle.grey,
                row=3)
            toggle_btn.callback = self._toggle_cosmetics_display
            self.add_item(toggle_btn)
            # --- END AI-GENERATED ---

        # Back button (row 3)
        back_btn = discord.ui.Button(label=_p('ui:inventory|button:back|label', 'Back'), emoji="\u2B05", style=discord.ButtonStyle.grey, row=3)
        back_btn.callback = self.go_back
        self.add_item(back_btn)

    def _make_filter_cb(self, filt):
        async def cb(interaction: discord.Interaction):
            self.active_filter = filt
            self.page = 0
            await self.load_items()
            self.refresh_buttons()
            await interaction.response.edit_message(embed=self.make_embed(), view=self)
        return cb

    def _make_equip_cb(self, item):
        async def cb(interaction: discord.Interaction):
            slot = item['slot']
            if not slot:
                await interaction.response.send_message(str(_p(
                    'error:inventory|cannot_equip',
                    "This item can't be equipped!")), ephemeral=True)
                return
            existing = await _db_fetch(self.cog.bot,
                "SELECT 1 FROM lg_pet_equipment WHERE userid = %s AND slot = %s",
                self.user_id, slot
            )
            if existing:
                await _db_exec(self.cog.bot,
                    "UPDATE lg_pet_equipment SET itemid = %s WHERE userid = %s AND slot = %s",
                    item['itemid'], self.user_id, slot
                )
            else:
                await _db_exec(self.cog.bot,
                    "INSERT INTO lg_pet_equipment (userid, slot, itemid) VALUES (%s, %s, %s)",
                    self.user_id, slot, item['itemid']
                )
            await self.load_items()
            self.refresh_buttons()
            await interaction.response.edit_message(embed=self.make_embed(), view=self)
        return cb

    def _make_unequip_cb(self, item):
        async def cb(interaction: discord.Interaction):
            await _db_exec(self.cog.bot,
                "DELETE FROM lg_pet_equipment WHERE userid = %s AND itemid = %s",
                self.user_id, item['itemid']
            )
            await self.load_items()
            self.refresh_buttons()
            await interaction.response.edit_message(embed=self.make_embed(), view=self)
        return cb

    # --- AI-GENERATED (2026-04-24) ---
    # Purpose: Cosmetic overlay write paths. _make_set_cosmetic_cb upserts
    # an lg_pet_cosmetics row so the renderer overlays the chosen item on
    # top of whatever is equipped for stats. _make_unset_cosmetic_cb deletes
    # the row, falling back to whatever (if anything) is in lg_pet_equipment
    # for that slot. _toggle_cosmetics_display flips the per-pet master
    # switch without wiping any cosmetic picks.
    def _make_set_cosmetic_cb(self, item):
        async def cb(interaction: discord.Interaction):
            slot = item['slot']
            if not slot:
                await interaction.response.send_message(str(_p(
                    'error:cosmetic|cannot_set',
                    "This item can't be used as a cosmetic!")), ephemeral=True)
                return
            existing = await _db_fetch(self.cog.bot,
                "SELECT 1 FROM lg_pet_cosmetics WHERE userid = %s AND slot = %s",
                self.user_id, slot
            )
            if existing:
                await _db_exec(self.cog.bot,
                    "UPDATE lg_pet_cosmetics SET itemid = %s, set_at = NOW() WHERE userid = %s AND slot = %s",
                    item['itemid'], self.user_id, slot
                )
            else:
                await _db_exec(self.cog.bot,
                    "INSERT INTO lg_pet_cosmetics (userid, slot, itemid) VALUES (%s, %s, %s)",
                    self.user_id, slot, item['itemid']
                )
            await self.load_items()
            self.refresh_buttons()
            await interaction.response.edit_message(embed=self.make_embed(), view=self)
        return cb

    def _make_unset_cosmetic_cb(self, item):
        async def cb(interaction: discord.Interaction):
            await _db_exec(self.cog.bot,
                "DELETE FROM lg_pet_cosmetics WHERE userid = %s AND itemid = %s",
                self.user_id, item['itemid']
            )
            await self.load_items()
            self.refresh_buttons()
            await interaction.response.edit_message(embed=self.make_embed(), view=self)
        return cb

    async def _toggle_cosmetics_display(self, interaction: discord.Interaction):
        await _db_exec(self.cog.bot,
            "UPDATE lg_pets SET cosmetics_enabled = NOT COALESCE(cosmetics_enabled, TRUE) WHERE userid = %s",
            self.user_id
        )
        await self.load_items()
        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)
    # --- END AI-GENERATED ---

    async def _go_enhance(self, interaction: discord.Interaction):
        view = EnhanceView(self.cog, self.user_id)
        await view.load_data()
        view.refresh_buttons()
        await interaction.response.edit_message(embed=view.make_embed(), view=view, attachments=[])

    async def prev_page(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def go_back(self, interaction: discord.Interaction):
        await self.cog._show_pet(interaction, edit=True)

# --- END AI-MODIFIED ---


# --- AI-GENERATED (2026-03-24) ---
# Purpose: Paginated inventory embed for the backpack button on the pet card
class InventoryPaginatorView(discord.ui.View):
    PAGE_SIZE = 10

    RARITY_ORDER = ['MYTHICAL', 'LEGENDARY', 'EPIC', 'RARE', 'UNCOMMON', 'COMMON']

    def __init__(self, cog, user_id: int, guild_id: int, items: list):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.items = items
        self.page = 0
        self.total_pages = max(1, (len(items) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self._build_buttons()

    def _build_buttons(self):
        self.clear_items()

        if self.total_pages > 1:
            prev_btn = discord.ui.Button(
                emoji="\u25C0", style=discord.ButtonStyle.grey, row=0,
                disabled=self.page == 0
            )
            prev_btn.callback = self._prev
            self.add_item(prev_btn)

            page_btn = discord.ui.Button(
                label=f"{self.page + 1}/{self.total_pages}",
                style=discord.ButtonStyle.grey, row=0, disabled=True
            )
            self.add_item(page_btn)

            next_btn = discord.ui.Button(
                emoji="\u25B6", style=discord.ButtonStyle.grey, row=0,
                disabled=self.page >= self.total_pages - 1
            )
            next_btn.callback = self._next
            self.add_item(next_btn)

        self.add_item(discord.ui.Button(
            label=_p('ui:backpack|button:equip|label', 'Equip'), emoji="\U0001F6E1\uFE0F",
            url=f"{WEBSITE_URL}/pet/inventory",
            style=discord.ButtonStyle.link, row=1
        ))
        self.add_item(discord.ui.Button(
            label=_p('ui:backpack|button:market|label', 'Buy & Sell'), emoji="\U0001F4B0",
            url=f"{WEBSITE_URL}/pet/marketplace",
            style=discord.ButtonStyle.link, row=1
        ))
        self.add_item(discord.ui.Button(
            label=_p('ui:backpack|button:enhance|label', 'Enhance'), emoji="\u2728",
            url=f"{WEBSITE_URL}/pet/enhancement",
            style=discord.ButtonStyle.link, row=1
        ))

    def _page_color(self) -> int:
        start = self.page * self.PAGE_SIZE
        page_items = self.items[start:start + self.PAGE_SIZE]
        for r in self.RARITY_ORDER:
            for it in page_items:
                if it['rarity'] == r:
                    return RARITY_EMBED_COLORS.get(r, 0x9e9e9e)
        return 0x9e9e9e

    def make_embed(self) -> discord.Embed:
        if not self.items:
            embed = discord.Embed(
                title=str(_p('embed:backpack|title', '\U0001F392 Your Backpack')),
                description=str(_p(
                    'embed:backpack|desc:empty',
                    'Your backpack is empty!\n\n'
                    'Earn items by being productive, farming, or buying from the marketplace.')),
                color=0x9e9e9e,
            )
            embed.set_footer(text=str(_p(
                'embed:backpack|footer:count', '{n} items')).format(n=0))
            return embed

        start = self.page * self.PAGE_SIZE
        page_items = self.items[start:start + self.PAGE_SIZE]
        lines = []
        for it in page_items:
            rarity = it['rarity']
            emoji = RARITY_EMOJI.get(rarity, '\u26AA')
            name = it['name']
            qty = it.get('qty', 1)
            enh = it.get('enhancement_level', 0)
            equipped = it.get('equipped', False)
            category = it.get('category', '')

            parts = [f"{emoji} **{name}**"]
            if enh > 0:
                max_enh = MAX_ENHANCEMENT_BY_RARITY.get(rarity, 5)
                parts.append(f"+{enh}/{max_enh}")
            if qty > 1:
                parts.append(f"x{qty}")
            tag = RARITY_LABELS.get(rarity, rarity.title())
            if category in ('SCROLL', 'CONSUMABLE', 'MATERIAL', 'FARM_SEED'):
                tag = f"{category.replace('_', ' ').title()}"
            parts.append(f"({tag})")
            if equipped:
                parts.append("\U0001F6E1\uFE0F")

            lines.append(" ".join(parts))

        total_items = sum(it.get('qty', 1) for it in self.items)
        embed = discord.Embed(
            title=str(_p('embed:backpack|title', '\U0001F392 Your Backpack')),
            description="\n".join(lines),
            color=self._page_color(),
        )
        embed.set_footer(text=str(_p(
            'embed:backpack|footer:page',
            'Page {cur}/{total} \u2022 {total_qty} total items \u2022 {unique} unique')).format(
                cur=self.page + 1, total=self.total_pages,
                total_qty=total_items, unique=len(self.items)))
        return embed

    async def _prev(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(str(_p(
                'error:backpack|not_yours', "This isn't your backpack!")), ephemeral=True)
            return
        self.page = max(0, self.page - 1)
        self._build_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your backpack!", ephemeral=True)
            return
        self.page = min(self.total_pages - 1, self.page + 1)
        self._build_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)
# --- END AI-GENERATED ---


# --- AI-REPLACED (2026-03-16) ---
# Reason: NPC shop removed -- only the player marketplace should exist for item trading
# What the new code does better: Removes unused ShopView; replaced by marketplace on website
# --- Original code (commented out for rollback) ---
# class ShopView(discord.ui.View):
#     def __init__(self, cog, user_id, guild_id): ...
#     async def load_items(self): ...
#     def make_embed(self): ...
#     def refresh_buttons(self): ...
#     def _make_buy_cb(self, item): ...
#     async def prev_page(self, interaction): ...
#     async def next_page(self, interaction): ...
#     async def go_back(self, interaction): ...
# --- End original code ---
# --- END AI-REPLACED ---


# --- AI-MODIFIED (2026-03-16) ---
# Purpose: Notification views and helpers for item drop alerts

RARITY_EMBED_COLORS = {
    'COMMON': 0x9e9e9e,
    'UNCOMMON': 0x4caf50,
    'RARE': 0x2196f3,
    'EPIC': 0x9c27b0,
    'LEGENDARY': 0xff9800,
    'MYTHICAL': 0xf44336,
}

RARITY_LABELS = {
    'COMMON': _p('rarity:common', 'Common'),
    'UNCOMMON': _p('rarity:uncommon', 'Uncommon'),
    'RARE': _p('rarity:rare', 'Rare'),
    'EPIC': _p('rarity:epic', 'Epic'),
    'LEGENDARY': _p('rarity:legendary', 'Legendary'),
    'MYTHICAL': _p('rarity:mythical', 'Mythical'),
}

RARITY_EMOJI = {
    'COMMON': '\u26AA',
    'UNCOMMON': '\U0001F7E2',
    'RARE': '\U0001F535',
    'EPIC': '\U0001F7E3',
    'LEGENDARY': '\U0001F7E0',
    'MYTHICAL': '\U0001F534',
}

def _clean_rarity(raw) -> str:
    """Normalize a rarity value to a clean uppercase string like 'COMMON'."""
    if isinstance(raw, str):
        s = raw
    elif hasattr(raw, 'value'):
        s = raw.value
    else:
        s = str(raw)
    if '.' in s:
        s = s.split('.')[-1]
    return s.upper()

NOTIF_COOLDOWN_SECONDS = 600
# --- AI-REPLACED (2026-03-20) ---
# Reason: 5% was too low for re-engagement; 12% gives non-pet users more exposure
# --- Original code (commented out for rollback) ---
# TEASER_CHANCE = 0.05
# --- End original code ---
# --- AI-MODIFIED (2026-03-21) ---
# Purpose: Temporarily disable server-channel teasers (users complained about spam)
# TEASER_CHANCE = 0.12
TEASER_CHANCE = 0
# --- END AI-MODIFIED ---
# --- END AI-REPLACED ---

# --- AI-MODIFIED (2026-04-10) ---
# Purpose: One-time adoption nudge system -- constants for rate-limiting and feature gating
NUDGE_HOURLY_CAP_PER_SHARD = 10
NUDGE_COOLDOWN_SECONDS = 5
_NUDGE_FEATURE_LAUNCH_TS = datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc)
_NUDGE_EXCLUDED_COMMANDS = frozenset({'pet', 'liongotchi-announce'})
# --- END AI-MODIFIED ---


# --- AI-REPLACED (2026-03-22) ---
# Reason: Views were not persistent -- buttons broke after every bot restart ("This interaction failed")
# What the new code does better: Adds custom_id to each button so discord.py can restore
#   handlers after restart. Uses interaction.user.id so any user gets their own pet/prefs.
#   Resolves cog reference dynamically via interaction.client.get_cog().
# --- Original code (commented out for rollback) ---
# class DropNotificationView(discord.ui.View):
#     def __init__(self, cog, user_id):
#         super().__init__(timeout=None)
#         self.cog = cog; self.user_id = user_id
#         self.add_item(Button(label="View Inventory", url=WEBSITE_URL+"/pet", style=ButtonStyle.link))
#     @discord.ui.button(label="Open Pet", emoji="🐾", style=ButtonStyle.green)
#     async def open_pet(self, interaction, button):
#         if interaction.user.id != self.user_id: return
#         await self.cog._show_pet(interaction)
#     @discord.ui.button(label="Mute Drops", emoji="🔕", style=ButtonStyle.grey)
#     async def mute_toggle(self, interaction, button):
#         if interaction.user.id != self.user_id: return
#         # ... toggle drop_notif for self.user_id ...
# class LevelUpNotificationView(discord.ui.View):  [same pattern]
# --- End original code ---

def _get_lg_cog(interaction: discord.Interaction) -> 'LionGotchiCog | None':
    return interaction.client.get_cog('LionGotchiCog')

# --- AI-REPLACED (2026-03-22) ---
# Reason: Both handlers lacked error handling, causing "This interaction failed" on any exception
# What the new code does better: Wraps all logic in try/except so the interaction ALWAYS gets a
#   response, and guards against double-response in _handle_open_pet
# --- Original code (commented out for rollback) ---
# async def _handle_open_pet(interaction):
#     cog = _get_lg_cog(interaction)
#     if not cog: ... return
#     try: await cog._show_pet(interaction)
#     except: await interaction.response.send_message(...)
#
# async def _handle_notif_toggle(interaction):
#     cog = _get_lg_cog(interaction)
#     if not cog: ... return
#     uid = interaction.user.id
#     rows = await _db_fetch(cog.bot, ...)
#     if not rows: ... return
#     ... cycle logic, _db_exec, response ...
# --- End original code ---
async def _handle_open_pet(interaction: discord.Interaction):
    cog = _get_lg_cog(interaction)
    if not cog:
        await interaction.response.send_message(
            str(_p('error:lg_reloading', 'LionGotchi is reloading, try again in a moment!')),
            ephemeral=True)
        return
    # --- AI-MODIFIED (2026-03-24) ---
    # Purpose: Handle errors gracefully after _show_pet may have deferred
    try:
        await cog._show_pet(interaction)
    except Exception:
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    str(_p('error:use_slash_pet', 'Use `/pet` in a server to see your LionGotchi!')),
                    ephemeral=True)
            else:
                await interaction.followup.send(
                    str(_p('error:pet_followup_failed', 'Something went wrong. Try `/pet` again!')),
                    ephemeral=True)
        except Exception:
            pass
    # --- END AI-MODIFIED ---

async def _handle_notif_toggle(interaction: discord.Interaction):
    cog = _get_lg_cog(interaction)
    if not cog:
        await interaction.response.send_message(
            str(_p('error:lg_reloading', 'LionGotchi is reloading, try again in a moment!')),
            ephemeral=True)
        return
    try:
        uid = interaction.user.id
        rows = await _db_fetch(cog.bot,
            "SELECT drop_notif FROM lg_pets WHERE userid = %s", uid)
        if not rows:
            await interaction.response.send_message(
                str(_p('error:no_pet_yet', "You don't have a pet yet!")), ephemeral=True)
            return
        current = rows[0].get('drop_notif') or 'ALL'
        if hasattr(current, 'value'):
            current = current.value
        cycle = {'ALL': 'DM_ONLY', 'DM_ONLY': 'MUTED', 'MUTED': 'ALL'}
        new_pref = cycle.get(current, 'ALL')
        await _db_exec(cog.bot,
            "UPDATE lg_pets SET drop_notif = %s WHERE userid = %s",
            new_pref, uid)
        labels = {
            'ALL': _p('notif:pref:channel_dm', 'Channel + DM'),
            'DM_ONLY': _p('notif:pref:dm_only', 'DM Only'),
            'MUTED': _p('notif:pref:muted', 'Muted'),
        }
        await interaction.response.send_message(
            str(_p(
                'notif:toggle:body',
                'LionGotchi notifications set to: **{pref}**\n'
                '(Click again to cycle: Channel+DM \u2192 DM Only \u2192 Muted)\n'
                '*This applies to drops, level-ups, and all pet notifications.*'
            )).format(pref=str(labels[new_pref])),
            ephemeral=True)
    except Exception:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                str(_p('error:generic_retry', 'Something went wrong, please try again!')),
                ephemeral=True)
# --- END AI-REPLACED ---


# --- AI-REPLACED (2026-04-07) ---
# Reason: Add 'View Item' wiki link button and update inventory link
# What the new code does better: Links directly to the dropped item's wiki page,
#   and points inventory link to /pet/inventory instead of generic /pet
# --- Original code (commented out for rollback) ---
# class DropNotificationView(discord.ui.View):
#     def __init__(self, cog=None, user_id=0):
#         super().__init__(timeout=None)
#         self.add_item(Button(label='View Inventory', url=f"{WEBSITE_URL}/pet", style=ButtonStyle.link))
#     @button(label='Open Pet', emoji="🐾", style=ButtonStyle.green, custom_id="lg:drop:open_pet")
#     async def open_pet(self, interaction, button): await _handle_open_pet(interaction)
#     @button(label='Mute Drops', emoji="🔕", style=ButtonStyle.grey, custom_id="lg:drop:mute_toggle")
#     async def mute_toggle(self, interaction, button): await _handle_notif_toggle(interaction)
# --- End original code ---
class DropNotificationView(discord.ui.View):
    """Persistent buttons attached to item drop DM notifications."""

    def __init__(self, cog: 'LionGotchiCog | None' = None, user_id: int = 0,
                 itemid: int = 0):
        super().__init__(timeout=None)
        if itemid:
            self.add_item(discord.ui.Button(
                label=_p('ui:drop_notif|button:view_item|label', 'View Item'),
                url=f"{WEBSITE_URL}/pet/wiki/{itemid}",
                emoji="\U0001F4D6",
                style=discord.ButtonStyle.link
            ))
        self.add_item(discord.ui.Button(
            label=_p('ui:drop_notif|button:view_inv|label', 'View Inventory'),
            url=f"{WEBSITE_URL}/pet/inventory",
            emoji="\U0001F4E6",
            style=discord.ButtonStyle.link
        ))

    @discord.ui.button(label=_p('ui:drop_notif|button:open_pet|label', 'Open Pet'), emoji="\U0001F43E",
                        style=discord.ButtonStyle.green,
                        custom_id="lg:drop:open_pet")
    async def open_pet(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_open_pet(interaction)

    @discord.ui.button(label=_p('ui:drop_notif|button:mute|label', 'Mute Drops'), emoji="\U0001F515",
                        style=discord.ButtonStyle.grey,
                        custom_id="lg:drop:mute_toggle")
    async def mute_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_notif_toggle(interaction)
# --- END AI-REPLACED ---


class LevelUpNotificationView(discord.ui.View):
    """Persistent buttons attached to level-up DM notifications."""

    def __init__(self, cog: 'LionGotchiCog | None' = None, user_id: int = 0):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            label=_p('ui:levelup_notif|button:view_pet|label', 'View Pet'),
            url=f"{WEBSITE_URL}/pet",
            style=discord.ButtonStyle.link
        ))

    @discord.ui.button(label=_p('ui:levelup_notif|button:open_pet|label', 'Open Pet'), emoji="\U0001F43E",
                        style=discord.ButtonStyle.green,
                        custom_id="lg:levelup:open_pet")
    async def open_pet(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_open_pet(interaction)

    @discord.ui.button(label=_p('ui:levelup_notif|button:notif_settings|label', 'Notification Settings'), emoji="\U0001F514",
                        style=discord.ButtonStyle.grey,
                        custom_id="lg:levelup:notif_toggle")
    async def notif_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_notif_toggle(interaction)
# --- END AI-REPLACED ---


class FirstEncounterView(discord.ui.View):
    """Rich button layout shown to users encountering LionGotchi for the first time."""

    def __init__(self, cog: 'LionGotchiCog', user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id

    # --- AI-MODIFIED (2026-03-20) ---
    # Purpose: Use async _build_embed_and_file for GIF-enabled onboarding
    @discord.ui.button(label=_p('ui:first_encounter|button:adopt|label', 'Adopt a Pet!'), emoji="\U0001F43E", style=discord.ButtonStyle.green, row=0)
    async def adopt_pet(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                str(_p('error:adopt_own_pet', 'Use `/pet` to adopt your own LionGotchi!')),
                ephemeral=True
            )
            return
        view = OnboardingView(self.cog, self.user_id)
        embed, gif_file = await view._build_embed_and_file()
        kwargs = {'embed': embed, 'view': view, 'ephemeral': True}
        if gif_file:
            kwargs['file'] = gif_file
        await interaction.response.send_message(**kwargs)
    # --- END AI-MODIFIED ---

    @discord.ui.button(label=_p('ui:first_encounter|button:learn_more|label', 'What is LionGotchi?'), emoji="\U0001F4D6", style=discord.ButtonStyle.blurple, row=0)
    async def learn_more(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title=str(_p('embed:what_is_lg|title', '\U0001F981 What is LionGotchi?')),
            color=0xffc107,
            description=str(_p(
                'embed:what_is_lg|desc',
                "**LionGotchi** is a virtual pet system built into LionBot!\n\n"
                "\U0001F43E **Adopt a pet** and raise it as you're productive\n"
                "\u2694\uFE0F **Earn equipment** and scrolls from activity\n"
                "\U0001F331 **Grow a farm** with seeds and harvest crops\n"
                "\U0001F3E0 **Decorate a room** with furniture and trophies\n"
                "\U0001F4B0 **Trade on the marketplace** with other users\n"
                "\u2B06\uFE0F **Enhance gear** for powerful bonuses\n\n"
                "The more productive you are, the more rewards you earn.\n"
                "Type `/pet` to get started!"
            ))
        )
        embed.set_footer(text=str(_p(
            'embed:what_is_lg|footer', 'Explore more at {url}'
        )).format(url=f"{WEBSITE_URL}/pet"))
        await interaction.response.send_message(embed=embed, ephemeral=True)


# --- AI-REPLACED (2026-03-22) ---
# Reason: View was not persistent -- buttons broke after bot restart
# What the new code does better: custom_id on each button, resolves cog dynamically
# --- Original code (commented out for rollback) ---
# class FirstDropView(discord.ui.View):
#     def __init__(self, cog, user_id):
#         super().__init__(timeout=None)
#         self.cog = cog; self.user_id = user_id
#         self.add_item(Button(label="View Inventory", url=WEBSITE_URL+"/pet", style=ButtonStyle.link))
#     @discord.ui.button(label="View Pet", emoji="🐾", style=ButtonStyle.green)
#     async def view_pet(self, interaction, button): ...
#     @discord.ui.button(label="Mute Notifications", emoji="🔕", style=ButtonStyle.grey)
#     async def mute_toggle(self, interaction, button): ...
# --- End original code ---
# --- AI-REPLACED (2026-04-07) ---
# Reason: Add 'View Item' wiki link and update inventory link for first drop
# What the new code does better: Links to item wiki page + inventory page
# --- Original code (commented out for rollback) ---
# class FirstDropView(discord.ui.View):
#     def __init__(self, cog=None, user_id=0):
#         super().__init__(timeout=None)
#         self.add_item(Button(label="View Inventory", url=f"{WEBSITE_URL}/pet", style=ButtonStyle.link))
#     @button(label="View Pet", emoji="🐾", style=ButtonStyle.green, custom_id="lg:firstdrop:view_pet")
#     async def view_pet(...): await _handle_open_pet(interaction)
#     @button(label="Mute Notifications", emoji="🔕", style=ButtonStyle.grey, custom_id="lg:firstdrop:mute_toggle")
#     async def mute_toggle(...): await _handle_notif_toggle(interaction)
# --- End original code ---
class FirstDropView(discord.ui.View):
    """Persistent buttons shown when a pet owner gets their very first item drop."""

    def __init__(self, cog: 'LionGotchiCog | None' = None, user_id: int = 0,
                 itemid: int = 0):
        super().__init__(timeout=None)
        if itemid:
            self.add_item(discord.ui.Button(
                label="View Item",
                url=f"{WEBSITE_URL}/pet/wiki/{itemid}",
                emoji="\U0001F4D6",
                style=discord.ButtonStyle.link
            ))
        self.add_item(discord.ui.Button(
            label="View Inventory",
            url=f"{WEBSITE_URL}/pet/inventory",
            emoji="\U0001F4E6",
            style=discord.ButtonStyle.link
        ))

    @discord.ui.button(label="View Pet", emoji="\U0001F43E",
                        style=discord.ButtonStyle.green,
                        custom_id="lg:firstdrop:view_pet")
    async def view_pet(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_open_pet(interaction)

    @discord.ui.button(label=_p('ui:first_drop|button:mute|label', 'Mute Notifications'), emoji="\U0001F515",
                        style=discord.ButtonStyle.grey,
                        custom_id="lg:firstdrop:mute_toggle")
    async def mute_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_notif_toggle(interaction)
# --- END AI-REPLACED ---


# --- AI-REPLACED (2026-03-20) ---
# Reason: Interactive Adopt button + website link for better conversion
# What the new code does better: "Adopt Now" opens the onboarding tutorial directly,
#   instead of just linking to the website
# --- Original code (commented out for rollback) ---
# class TeaserView(discord.ui.View):
#     def __init__(self):
#         super().__init__(timeout=None)
#         self.add_item(Button(label="Get Started", url=..., style=ButtonStyle.link))
# --- End original code ---
class TeaserView(discord.ui.View):
    """Buttons for non-pet-owner teaser messages with interactive adopt option."""

    def __init__(self, cog: 'LionGotchiCog' = None, user_id: int = 0):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        self.add_item(discord.ui.Button(
            label=_p('ui:teaser|button:learn_more|label', 'Learn More'),
            url=f"{WEBSITE_URL}/pet",
            style=discord.ButtonStyle.link
        ))

    @discord.ui.button(label=_p('ui:teaser|button:adopt|label', 'Adopt Now!'), emoji="\U0001F43E", style=discord.ButtonStyle.green)
    async def adopt_now(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.cog:
            await interaction.response.send_message(
                str(_p('error:adopt_slash_pet', 'Use `/pet` to adopt your LionGotchi!')),
                ephemeral=True
            )
            return
        view = OnboardingView(self.cog, interaction.user.id)
        embed, gif_file = await view._build_embed_and_file()
        kwargs = {'embed': embed, 'view': view, 'ephemeral': True}
        if gif_file:
            kwargs['file'] = gif_file
        await interaction.response.send_message(**kwargs)
# --- END AI-REPLACED ---

# --- AI-MODIFIED (2026-04-10) ---
# Purpose: Persistent view for one-time adoption nudge DMs -- buttons survive bot restarts
class AdoptionNudgeView(discord.ui.View):
    """Buttons for the one-time adoption nudge DM. Persistent via custom_id."""

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            label='Learn More',
            url=f"{WEBSITE_URL}/pet/tutorial",
            style=discord.ButtonStyle.link,
        ))

    @discord.ui.button(
        label='Adopt Now!',
        emoji="\U0001F43E",
        style=discord.ButtonStyle.green,
        custom_id='lg:nudge:adopt',
    )
    async def adopt_now(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog('LionGotchiCog')
        if not cog:
            await interaction.response.send_message(
                'Use `/pet` to adopt your LionGotchi!',
                ephemeral=True,
            )
            return
        view = OnboardingView(cog, interaction.user.id)
        embed, gif_file = await view._build_embed_and_file()
        kwargs = {'embed': embed, 'view': view, 'ephemeral': True}
        if gif_file:
            kwargs['file'] = gif_file
        await interaction.response.send_message(**kwargs)
# --- END AI-MODIFIED ---


# --- AI-REPLACED (2026-03-16) ---
# Reason: Crafting system removed -- equipment and scrolls now drop directly from activity
# What the new code does better: No more crafting; items drop naturally
# --- Original code (commented out for rollback) ---
# class CraftView(discord.ui.View):
#     """Crafting interface -- pick a recipe, see ingredients, craft."""
#     def __init__(self, cog, user_id, guild_id):
#         ... recipes, user_materials, load_recipes, _get_ingredients, _can_craft ...
#     def make_embed(self): ...
#     def _detail_embed(self): ...
#     def refresh_buttons(self): ...
#     def _build_list_buttons(self): ...
#     def _build_detail_buttons(self): ...
#     async def _on_recipe_selected(self, interaction): ...
#     async def _do_craft(self, interaction): ...
#     async def _back_to_list(self, interaction): ...
#     async def go_back(self, interaction): ...
# --- End original code ---
# CraftView has been removed. Crafting is no longer available.
# --- END AI-REPLACED ---

# --- END AI-MODIFIED ---


# --- AI-MODIFIED (2026-03-15) ---
# Purpose: EnhanceView for enhancing equipment with scrolls

class EnhanceView(discord.ui.View):
    """Enhancement interface -- pick equipment, pick scroll, attempt enhance."""

    def __init__(self, cog: 'LionGotchiCog', user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.equipment_items = []
        self.scroll_items = []
        self.selected_equip = None
        self.selected_scroll = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def load_data(self):
        self.equipment_items = await _db_fetch(self.cog.bot,
            """SELECT ui.inventoryid, ui.itemid, ui.enhancement_level,
                      i.name, i.rarity, i.slot, i.category
               FROM lg_user_inventory ui
               JOIN lg_items i ON ui.itemid = i.itemid
               WHERE ui.userid = %s
                 AND i.category NOT IN ('MATERIAL', 'SCROLL', 'FURNITURE', 'ROOM',
                                        'GAMEBOY_SKIN', 'FARM_SEED', 'CONSUMABLE')
                 AND i.slot IS NOT NULL
               ORDER BY ui.enhancement_level DESC, i.rarity DESC, i.name""",
            self.user_id
        ) or []

        # --- AI-MODIFIED (2026-03-17) ---
        # Purpose: Include bonus_value in scroll data for display
        self.scroll_items = await _db_fetch(self.cog.bot,
            """SELECT ui.inventoryid, ui.itemid, ui.quantity,
                      i.name, i.rarity,
                      sp.success_rate, sp.destroy_rate, sp.bonus_value
               FROM lg_user_inventory ui
               JOIN lg_items i ON ui.itemid = i.itemid
               JOIN lg_scroll_properties sp ON sp.itemid = i.itemid
               WHERE ui.userid = %s AND i.category = 'SCROLL' AND ui.quantity > 0
               ORDER BY sp.bonus_value DESC, sp.success_rate DESC""",
            self.user_id
        ) or []
        # --- END AI-MODIFIED ---

    def make_embed(self) -> discord.Embed:
        if self.selected_equip and self.selected_scroll:
            return self._confirm_embed()
        if self.selected_equip:
            return self._scroll_select_embed()
        return self._equip_select_embed()

    def _equip_select_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=str(_p('embed:enhance|title', '\u2728 Enhancement')),
            color=discord.Color.purple())
        if not self.equipment_items:
            embed.description = str(_p(
                'embed:enhance|desc:no_equip',
                'You have no equipment to enhance. Get items from the shop or crafting!'))
            return embed
        lines = []
        for eq in self.equipment_items[:25]:
            lvl = eq['enhancement_level'] or 0
            rarity = eq['rarity'] if isinstance(eq['rarity'], str) else str(eq['rarity'])
            max_lvl = MAX_ENHANCEMENT_BY_RARITY.get(rarity, 5)
            name = f"**{eq['name']}** +{lvl}" if lvl > 0 else f"**{eq['name']}**"
            lines.append(f"{name} ({rarity}) [{lvl}/{max_lvl}]")
        embed.description = str(_p(
            'embed:enhance|desc:pick_equip', 'Select an equipment item to enhance:\n\n'
        )) + "\n".join(lines)
        embed.set_footer(text=str(_p(
            'embed:enhance|footer:scroll_count', 'You have {n} scroll type(s) available'
        )).format(n=len(self.scroll_items)))
        return embed

    def _scroll_select_embed(self) -> discord.Embed:
        eq = self.selected_equip
        lvl = eq['enhancement_level'] or 0
        rarity = eq['rarity'] if isinstance(eq['rarity'], str) else str(eq['rarity'])
        embed = discord.Embed(
            title=str(_p(
                'embed:enhance|title:with_item', '\u2728 Enhance: {name} +{lvl}'
            )).format(name=eq['name'], lvl=lvl),
            color=discord.Color.purple()
        )
        if not self.scroll_items:
            embed.description = str(_p(
                'embed:enhance|desc:no_scrolls',
                'You have no scrolls! Keep being productive to earn scroll drops.'))
            return embed
        # --- AI-MODIFIED (2026-03-17) ---
        # Purpose: Show bonus_value info alongside success/destroy rates
        lines = []
        for s in self.scroll_items:
            # --- AI-REPLACED (2026-03-22) ---
            # Reason: Old linear penalty replaced with diminishing-returns curve
            # --- Original code (commented out for rollback) ---
            # eff_rate = float(s['success_rate']) * max(0.1, 1.0 - LEVEL_PENALTY_FACTOR * lvl)
            # --- End original code ---
            eff_rate = float(s['success_rate']) * calc_level_penalty(lvl)
            # --- END AI-REPLACED ---
            bv = float(s.get('bonus_value', 1.0))
            gold_pct = bv * ENHANCEMENT_GOLD_BONUS * 100
            lines.append(str(_p(
                'embed:enhance|desc:scroll_line',
                '**{name}** x{qty}\n'
                '  Success: {succ}% | Destroy: {dest}% | Bonus: **+{gold}%** Gold/XP'
            )).format(
                name=s['name'], qty=s['quantity'],
                succ=f'{eff_rate*100:.0f}', dest=f'{float(s["destroy_rate"])*100:.0f}',
                gold=f'{gold_pct:.1f}',
            ))
        embed.description = str(_p(
            'embed:enhance|desc:pick_scroll', 'Select a scroll:\n\n'
        )) + "\n".join(lines)
        # --- END AI-MODIFIED ---
        return embed

    def _confirm_embed(self) -> discord.Embed:
        eq = self.selected_equip
        sc = self.selected_scroll
        lvl = eq['enhancement_level'] or 0
        rarity = eq['rarity'] if isinstance(eq['rarity'], str) else str(eq['rarity'])
        max_lvl = MAX_ENHANCEMENT_BY_RARITY.get(rarity, 5)
        # --- AI-REPLACED (2026-03-22) ---
        # Reason: Old linear penalty replaced with diminishing-returns curve
        # --- Original code (commented out for rollback) ---
        # eff_rate = float(sc['success_rate']) * max(0.1, 1.0 - LEVEL_PENALTY_FACTOR * lvl)
        # --- End original code ---
        eff_rate = float(sc['success_rate']) * calc_level_penalty(lvl)
        # --- END AI-REPLACED ---

        embed = discord.Embed(
            title=str(_p(
                'embed:enhance|title:confirm',
                '\u2728 Enhance {name} +{lvl} -> +{next_lvl}'
            )).format(name=eq['name'], lvl=lvl, next_lvl=lvl + 1),
            color=discord.Color.purple()
        )
        # --- AI-MODIFIED (2026-03-17) ---
        # Purpose: Show scroll bonus_value in confirm embed
        bv = float(sc.get('bonus_value', 1.0))
        gold_gain = bv * ENHANCEMENT_GOLD_BONUS * 100
        drop_gain = bv * ENHANCEMENT_DROP_BONUS * 100
        embed.description = str(_p(
            'embed:enhance|desc:confirm_body',
            '**Item:** {iname} +{lvl} ({rarity}) [{lvl}/{max_lvl}]\n'
            '**Scroll:** {sname} (x{sqty})\n\n'
            '**Success Rate:** {srate}%\n'
            '**Destroy on Fail:** {drate}%\n'
            '**Bonus on Success:** +{gold}% Gold/XP, +{drop}% Drop Rate\n\n'
        )).format(
            iname=eq['name'], lvl=lvl, rarity=rarity, max_lvl=max_lvl,
            sname=sc['name'], sqty=sc['quantity'],
            srate=f'{eff_rate*100:.0f}', drate=f'{float(sc["destroy_rate"])*100:.0f}',
            gold=f'{gold_gain:.1f}', drop=f'{drop_gain:.2f}',
        )
        if float(sc['destroy_rate']) > 0:
            embed.description += str(_p(
                'embed:enhance|desc:warn_destroy',
                '\u26A0\uFE0F If enhancement fails, there is a chance your item will be **destroyed**!'))
        else:
            embed.description += str(_p(
                'embed:enhance|desc:no_destroy',
                '\u2705 This scroll has **0% destroy chance**.'))
        embed.set_footer(text=str(_p(
            'embed:enhance|footer:confirm',
            'Bonus value: {bv}x | Higher risk scrolls give more stats per level!'
        )).format(bv=f'{bv:.1f}'))
        # --- END AI-MODIFIED ---
        return embed

    def refresh_buttons(self):
        self.clear_items()
        if self.selected_equip and self.selected_scroll:
            self._build_confirm_buttons()
        elif self.selected_equip:
            self._build_scroll_select()
        else:
            self._build_equip_select()

    def _build_equip_select(self):
        if self.equipment_items:
            options = []
            for eq in self.equipment_items[:25]:
                lvl = eq['enhancement_level'] or 0
                rarity = eq['rarity'] if isinstance(eq['rarity'], str) else str(eq['rarity'])
                label = f"{eq['name']} +{lvl}" if lvl else eq['name']
                options.append(discord.SelectOption(
                    label=label[:100], value=str(eq['inventoryid']),
                    description=f"{rarity} | {eq['slot']}"
                ))
            select = discord.ui.Select(
                placeholder=str(_p('ui:enhance|select:equip_placeholder', 'Select equipment...')),
                options=options, row=0)
            select.callback = self._on_equip_selected
            self.add_item(select)

        back_btn = discord.ui.Button(
            label=_p('ui:enhance|button:back|label', 'Back'), emoji="\u2B05",
            style=discord.ButtonStyle.grey, row=1)
        back_btn.callback = self.go_back
        self.add_item(back_btn)

    def _build_scroll_select(self):
        if self.scroll_items:
            options = []
            eq_lvl = self.selected_equip['enhancement_level'] or 0
            # --- AI-MODIFIED (2026-03-17) ---
            # Purpose: Show bonus_value in scroll dropdown description
            for s in self.scroll_items:
                # --- AI-REPLACED (2026-03-22) ---
                # Reason: Old linear penalty replaced with diminishing-returns curve
                # --- Original code (commented out for rollback) ---
                # eff = float(s['success_rate']) * max(0.1, 1.0 - LEVEL_PENALTY_FACTOR * eq_lvl)
                # --- End original code ---
                eff = float(s['success_rate']) * calc_level_penalty(eq_lvl)
                # --- END AI-REPLACED ---
                bv = float(s.get('bonus_value', 1.0))
                options.append(discord.SelectOption(
                    label=f"{s['name']} (x{s['quantity']})"[:100],
                    value=str(s['itemid']),
                    description=str(_p(
                        'ui:enhance|option:scroll_stats',
                        '{eff}% OK | {dest}% Destroy | {bv}x Bonus'
                    )).format(
                        eff=f'{eff*100:.0f}',
                        dest=f'{float(s["destroy_rate"])*100:.0f}',
                        bv=f'{bv:.1f}',
                    )
                ))
            # --- END AI-MODIFIED ---
            select = discord.ui.Select(
                placeholder=str(_p('ui:enhance|select:scroll_placeholder', 'Select a scroll...')),
                options=options, row=0)
            select.callback = self._on_scroll_selected
            self.add_item(select)

        back_btn = discord.ui.Button(
            label=_p('ui:enhance|button:back_items|label', 'Back to Items'), emoji="\u2B05",
            style=discord.ButtonStyle.grey, row=1)
        back_btn.callback = self._back_to_equip
        self.add_item(back_btn)

    def _build_confirm_buttons(self):
        enhance_btn = discord.ui.Button(
            label=_p('ui:enhance|button:enhance|label', 'Enhance!'), emoji="\u2728",
            style=discord.ButtonStyle.danger, row=0)
        enhance_btn.callback = self._do_enhance
        self.add_item(enhance_btn)

        cancel_btn = discord.ui.Button(
            label=_p('ui:enhance|button:cancel|label', 'Cancel'), emoji="\u274C",
            style=discord.ButtonStyle.grey, row=0)
        cancel_btn.callback = self._back_to_equip
        self.add_item(cancel_btn)

    async def _on_equip_selected(self, interaction: discord.Interaction):
        inv_id = int(interaction.data['values'][0])
        self.selected_equip = next((e for e in self.equipment_items if e['inventoryid'] == inv_id), None)
        self.selected_scroll = None
        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def _on_scroll_selected(self, interaction: discord.Interaction):
        scroll_itemid = int(interaction.data['values'][0])
        self.selected_scroll = next((s for s in self.scroll_items if s['itemid'] == scroll_itemid), None)
        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def _do_enhance(self, interaction: discord.Interaction):
        if not self.selected_equip or not self.selected_scroll:
            return
        result = await attempt_enhance(
            self.cog.bot, self.user_id,
            self.selected_equip['inventoryid'],
            self.selected_scroll['itemid']
        )

        if result['error']:
            await interaction.response.send_message(result['error'], ephemeral=True)
            return

        if result['success']:
            # --- AI-MODIFIED (2026-03-17) ---
            # Purpose: Show bonus gained from scroll and glow tier on success
            bv = result.get('bonus_gained', 1.0)
            gold_gain = bv * ENHANCEMENT_GOLD_BONUS * 100
            glow = result.get('glow_tier', 'none')
            glow_text = (
                str(_p('embed:enhance|glow_suffix', ' | Glow: **{glow}**')).format(
                    glow=glow.capitalize())
                if glow != 'none' else "")
            embed = discord.Embed(
                title=str(_p('embed:enhance|title:success', '\u2728 Enhancement Success!')),
                description=str(_p(
                    'embed:enhance|desc:success',
                    '**{item}** is now **+{lvl}**!\n\n'
                    'Gained: **+{gold}%** Gold/XP from this scroll{glow}'
                )).format(
                    item=self.selected_equip['name'], lvl=result['new_level'],
                    gold=f'{gold_gain:.1f}', glow=glow_text,
                ),
                color=discord.Color.green()
            )
            # --- END AI-MODIFIED ---
        elif result['destroyed']:
            embed = discord.Embed(
                title=str(_p('embed:enhance|title:destroyed', '\U0001F4A5 Item Destroyed!')),
                description=str(_p(
                    'embed:enhance|desc:destroyed',
                    '**{item}** was **destroyed** during enhancement.\n'
                    'The scroll was consumed.'
                )).format(item=self.selected_equip['name']),
                color=discord.Color.red()
            )
        else:
            embed = discord.Embed(
                title=str(_p('embed:enhance|title:failed', '\u274C Enhancement Failed')),
                description=str(_p(
                    'embed:enhance|desc:failed',
                    '**{item}** remains at +{lvl}.\n'
                    'The scroll was consumed, but the item survived.'
                )).format(item=self.selected_equip['name'], lvl=result['new_level']),
                color=discord.Color.orange()
            )

        self.selected_equip = None
        self.selected_scroll = None
        await self.load_data()
        self.refresh_buttons()
        await interaction.response.edit_message(embed=embed, view=self)

    async def _back_to_equip(self, interaction: discord.Interaction):
        self.selected_equip = None
        self.selected_scroll = None
        await self.load_data()
        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def go_back(self, interaction: discord.Interaction):
        await self.cog._show_pet(interaction, edit=True)

# --- END AI-MODIFIED ---


FURNITURE_SLOTS = ['wall', 'floor', 'mat', 'table', 'chair', 'bed', 'lamp', 'picture', 'window']
SLOT_EMOJIS = {
    'wall': '\U0001F3E0', 'floor': '\U0001F7EB', 'mat': '\U0001F9F6',
    'table': '\U0001FA91', 'chair': '\U0001FA91', 'bed': '\U0001F6CF',
    'lamp': '\U0001F4A1', 'picture': '\U0001F5BC', 'window': '\U0001FA9F',
}


class RoomView(discord.ui.View):
    """Room customization -- pick a furniture slot, then choose a piece for it."""

    def __init__(self, cog: 'LionGotchiCog', user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.active_slot = None
        self.current_parts = {}
        self.available_items = []

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def load_current_parts(self):
        rows = await _db_fetch(self.cog.bot,
            """SELECT slot, asset_path FROM lg_user_furniture
               WHERE userid = %s""",
            self.user_id
        )
        self.current_parts = {r['slot']: r['asset_path'] for r in (rows or [])}

    async def load_items_for_slot(self, slot_name: str):
        search = f"%{slot_name}%"
        self.available_items = await _db_fetch(self.cog.bot,
            """SELECT i.itemid, i.name, i.gold_price, i.asset_path
               FROM lg_items i
               WHERE i.category = 'FURNITURE' AND i.asset_path LIKE %s
               ORDER BY i.gold_price NULLS LAST, i.name""",
            search
        ) or []

    def make_embed(self) -> discord.Embed:
        if self.active_slot:
            embed = discord.Embed(
                title=str(_p('embed:room|title:slot', 'Room - {slot}')).format(
                    slot=self.active_slot.title()),
                color=discord.Color.blue()
            )
            current = self.current_parts.get(self.active_slot, 'default')
            cur_name = current.split('/')[-1].replace('.png', '').replace('_', ' ').title()
            embed.description = str(_p(
                'embed:room|desc:current',
                'Current: **{name}**\n\nChoose a replacement:'
            )).format(name=cur_name)
            if not self.available_items:
                embed.description += str(_p(
                    'embed:room|desc:no_items',
                    '\n\nNo items available for this slot yet.'
                ))
        else:
            embed = discord.Embed(
                title=_p('embed:room|title', 'Room Customization'),
                color=discord.Color.blue())
            lines = [str(_p('embed:room|desc:pick_slot', 'Pick a furniture slot to customize:\n'))]
            default_lbl = str(_p('embed:room|default_name', 'Default'))
            for slot in FURNITURE_SLOTS:
                current = self.current_parts.get(slot)
                if current:
                    name = current.split('/')[-1].replace('.png', '').replace('_', ' ').title()
                else:
                    name = default_lbl
                lines.append(f"**{slot.title()}**: {name}")
            embed.description = "\n".join(lines)
        return embed

    def refresh_buttons(self):
        self.clear_items()
        if self.active_slot:
            for it in self.available_items[:5]:
                owned = any(p == it['asset_path'] for p in self.current_parts.values())
                label = it['name'][:20]
                if not owned and it['gold_price']:
                    label += f" ({it['gold_price']}G)"
                btn = discord.ui.Button(label=label, style=discord.ButtonStyle.green, row=0)
                btn.callback = self._make_place_cb(it)
                self.add_item(btn)

            if len(self.available_items) > 5:
                for it in self.available_items[5:10]:
                    label = it['name'][:20]
                    if it['gold_price']:
                        label += f" ({it['gold_price']}G)"
                    btn = discord.ui.Button(label=label, style=discord.ButtonStyle.green, row=1)
                    btn.callback = self._make_place_cb(it)
                    self.add_item(btn)

            slots_btn = discord.ui.Button(
                label=_p('ui:room|button:back_slots|label', 'Back to Slots'),
                emoji="\u2B05", style=discord.ButtonStyle.grey, row=2)
            slots_btn.callback = self.back_to_slots
            self.add_item(slots_btn)
        else:
            row = 0
            for i, slot in enumerate(FURNITURE_SLOTS):
                if i == 5:
                    row = 1
                btn = discord.ui.Button(label=slot.title(), style=discord.ButtonStyle.blurple, row=row)
                btn.callback = self._make_slot_cb(slot)
                self.add_item(btn)

            back_btn = discord.ui.Button(
                label=_p('ui:room|button:back|label', 'Back'),
                emoji="\u2B05", style=discord.ButtonStyle.grey, row=2)
            back_btn.callback = self.go_back
            self.add_item(back_btn)

    def _make_slot_cb(self, slot_name):
        async def cb(interaction: discord.Interaction):
            self.active_slot = slot_name
            await self.load_items_for_slot(slot_name)
            self.refresh_buttons()
            await interaction.response.edit_message(embed=self.make_embed(), view=self)
        return cb

    def _make_place_cb(self, item):
        async def cb(interaction: discord.Interaction):
            existing = await _db_fetch(self.cog.bot,
                "SELECT 1 FROM lg_user_inventory WHERE userid = %s AND itemid = %s",
                self.user_id, item['itemid']
            )
            if not existing:
                price = item['gold_price'] or 0
                if price > 0:
                    balance = await _db_fetch(self.cog.bot,
                        "SELECT gold FROM user_config WHERE userid = %s", self.user_id
                    )
                    current_gold = balance[0]['gold'] if balance else 0
                    if current_gold < price:
                        await interaction.response.send_message(
                            str(_p(
                                'error:room|not_enough_gold',
                                'Not enough Gold! Need {need}, have {have}.'
                            )).format(need=price, have=current_gold),
                            ephemeral=True
                        )
                        return
                    await _db_exec(self.cog.bot,
                        "UPDATE user_config SET gold = gold - %s WHERE userid = %s",
                        price, self.user_id
                    )
                await _db_exec(self.cog.bot,
                    "INSERT INTO lg_user_inventory (userid, itemid, source) VALUES (%s, %s, %s)",
                    self.user_id, item['itemid'], 'SHOP'
                )

            slot = self.active_slot
            already = await _db_fetch(self.cog.bot,
                "SELECT 1 FROM lg_user_furniture WHERE userid = %s AND slot = %s",
                self.user_id, slot
            )
            if already:
                await _db_exec(self.cog.bot,
                    "UPDATE lg_user_furniture SET asset_path = %s WHERE userid = %s AND slot = %s",
                    item['asset_path'], self.user_id, slot
                )
            else:
                await _db_exec(self.cog.bot,
                    "INSERT INTO lg_user_furniture (userid, slot, asset_path) VALUES (%s, %s, %s)",
                    self.user_id, slot, item['asset_path']
                )

            self.current_parts[slot] = item['asset_path']
            self.refresh_buttons()
            await interaction.response.edit_message(embed=self.make_embed(), view=self)
        return cb

    async def back_to_slots(self, interaction: discord.Interaction):
        self.active_slot = None
        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def go_back(self, interaction: discord.Interaction):
        await self.cog._show_pet(interaction, edit=True)


class SkinView(discord.ui.View):
    def __init__(self, cog: 'LionGotchiCog', user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.skins = []
        self.page = 0
        self.page_size = 5

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    # --- AI-REPLACED (2026-03-17) ---
    # Reason: Old query only showed FREE/LEVEL skins. Now skins are FREE or GEMS.
    # What the new code does better: Also shows GEMS skins the user has purchased via lg_user_gameboy_skins
    # --- Original code (commented out for rollback) ---
    # async def load_skins(self):
    #     self.skins = await _db_fetch(self.cog.bot,
    #         """SELECT s.skin_id, s.theme, s.color, s.unlock_type,
    #                   p.active_gameboy_skin_id = s.skin_id AS active
    #            FROM lg_gameboy_skins s
    #            LEFT JOIN lg_pets p ON p.userid = %s
    #            WHERE s.unlock_type = 'FREE' OR s.unlock_type = 'LEVEL'
    #            ORDER BY s.theme, s.color""",
    #         self.user_id
    #     ) or []
    # --- End original code ---
    async def load_skins(self):
        self.skins = await _db_fetch(self.cog.bot,
            """SELECT s.skin_id, s.theme, s.color, s.unlock_type,
                      p.active_gameboy_skin_id = s.skin_id AS active
               FROM lg_gameboy_skins s
               LEFT JOIN lg_pets p ON p.userid = %s
               LEFT JOIN lg_user_gameboy_skins o ON o.userid = %s AND o.skin_id = s.skin_id
               WHERE s.unlock_type = 'FREE'
                  OR s.unlock_type = 'LEVEL'
                  OR (s.unlock_type = 'GEMS' AND o.skin_id IS NOT NULL)
               ORDER BY s.theme, s.color""",
            self.user_id, self.user_id
        ) or []
    # --- END AI-REPLACED ---

    def make_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=_p('embed:skins|title', 'Gameboy Skins'),
            color=discord.Color.purple())
        start = self.page * self.page_size
        page_skins = self.skins[start:start + self.page_size]
        lines = []
        active_suffix = str(_p('embed:skins|active_suffix', ' [ACTIVE]'))
        for s in page_skins:
            active = active_suffix if s['active'] else ""
            lines.append(f"**{s['theme'].replace('_',' ').title()} {s['color'].title()}**{active}")
        embed.description = (
            "\n".join(lines) if lines else str(_p('embed:skins|desc:empty', 'No skins available.')))
        total_pages = max(1, (len(self.skins) + self.page_size - 1) // self.page_size)
        embed.set_footer(text=str(_p(
            'embed:skins|footer:page', 'Page {cur}/{total}')).format(
                cur=self.page + 1, total=total_pages))
        return embed

    def refresh_buttons(self):
        self.clear_items()
        total_pages = max(1, (len(self.skins) + self.page_size - 1) // self.page_size)
        if total_pages > 1:
            prev_btn = discord.ui.Button(
                label=_p('ui:skins|button:prev|label', '<'),
                style=discord.ButtonStyle.grey, row=0, disabled=self.page == 0)
            prev_btn.callback = self.prev_page
            self.add_item(prev_btn)
            next_btn = discord.ui.Button(
                label=_p('ui:skins|button:next|label', '>'),
                style=discord.ButtonStyle.grey, row=0, disabled=self.page >= total_pages - 1)
            next_btn.callback = self.next_page
            self.add_item(next_btn)

        start = self.page * self.page_size
        page_skins = self.skins[start:start + self.page_size]
        for s in page_skins:
            if s['active']:
                continue
            label = f"{s['theme'].replace('_',' ').title()} {s['color'].title()}"
            btn = discord.ui.Button(label=label[:20], style=discord.ButtonStyle.green, row=1)
            btn.callback = self._make_select_cb(s)
            self.add_item(btn)

        back_btn = discord.ui.Button(
            label=_p('ui:skins|button:back|label', 'Back'),
            emoji="\u2B05", style=discord.ButtonStyle.grey, row=2)
        back_btn.callback = self.go_back
        self.add_item(back_btn)

    def _make_select_cb(self, skin):
        async def cb(interaction: discord.Interaction):
            await _db_exec(self.cog.bot,
                "UPDATE lg_pets SET active_gameboy_skin_id = %s WHERE userid = %s",
                skin['skin_id'], self.user_id
            )
            await self.load_skins()
            self.refresh_buttons()
            await interaction.response.edit_message(embed=self.make_embed(), view=self)
        return cb

    async def prev_page(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def go_back(self, interaction: discord.Interaction):
        await self.cog._show_pet(interaction, edit=True)


# ============================================================
# Farm View
# ============================================================
DRY_DEATH_HOURS = 48


# --- AI-MODIFIED (2026-03-15) ---
# Purpose: Added fullscreen toggle support to FarmView
class FarmView(discord.ui.View):
    """Farm view with dropdown plot selection and action buttons."""

    def __init__(self, cog: 'LionGotchiCog', user_id: int, guild: discord.Guild = None,
                 fullscreen: bool = False):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.guild = guild
        self.plots = []
        self._cached_pet_state = None
        self.fullscreen = fullscreen
        self.user_tier = 'NONE'
# --- END AI-MODIFIED ---

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: Fetch activity-driven columns + cache user_tier for harvest gold display
    async def load_farm(self):
        self.plots = await _db_fetch(self.cog.bot,
            """SELECT f.plot_id, f.seed_id, f.planted_at, f.last_watered,
                      f.growth_stage, f.dead,
                      f.growth_points, f.gold_invested,
                      f.voice_minutes_earned, f.messages_earned,
                      f.rarity,
                      s.name AS seed_name, s.plant_type, s.grow_time_hours,
                      s.water_interval_hours, s.harvest_gold, s.asset_prefix,
                      s.plant_cost, s.growth_points_needed
               FROM lg_user_farm f
               LEFT JOIN lg_farm_seeds s ON f.seed_id = s.seed_id
               WHERE f.userid = %s
               ORDER BY f.plot_id""",
            self.user_id
        ) or []
        tier_result, _ = await self.cog._get_premium_context(
            self.user_id, self.guild.id if self.guild else None)
        self.user_tier = tier_result or 'NONE'
        await self._update_growth()
    # --- END AI-MODIFIED ---

    # --- AI-REPLACED (2026-03-15) ---
    # Reason: Growth is now activity-driven (handled in gameplay.py). This only checks death.
    # What the new code does better: Simplified to death-check only; growth logic in process_farm_growth()
    # --- Original code (commented out for rollback) ---
    # async def _update_growth(self):
    #     now = datetime.now(timezone.utc)
    #     for plot in self.plots:
    #         ... time-based growth calculation using planted_at and DEV_GROWTH_SPEED ...
    #         ... advance growth_stage based on elapsed time ...
    # --- End original code ---
    async def _update_growth(self):
        """Only check for death from prolonged dryness. Growth is handled by activity."""
        now = datetime.now(timezone.utc)
        for plot in self.plots:
            if not plot['seed_id'] or plot['dead'] or plot['growth_stage'] >= 5:
                continue
            last_watered = plot['last_watered']
            if last_watered is None:
                continue
            if last_watered.tzinfo is None:
                last_watered = last_watered.replace(tzinfo=timezone.utc)
            hours_since_water = (now - last_watered).total_seconds() / 3600
            if hours_since_water > DRY_DEATH_HOURS:
                await _db_exec(self.cog.bot,
                    "UPDATE lg_user_farm SET dead = true WHERE userid = %s AND plot_id = %s",
                    self.user_id, plot['plot_id'])
                plot['dead'] = True
    # --- END AI-REPLACED ---

    # --- AI-REPLACED (2026-03-15) ---
    # Reason: Activity-driven growth display with points progress instead of time timers
    # What the new code does better: Shows growth points progress, removes DEV_GROWTH_SPEED references
    # --- Original code (commented out for rollback) ---
    # def _build_farm_state(self, just_watered=False):
    #     ... time-based timer calculations using DEV_GROWTH_SPEED, planted_at, etc. ...
    # --- End original code ---
    def _build_farm_state(self, just_watered: bool = False) -> FarmState:
        now = datetime.now(timezone.utc)
        is_night = now.hour < 6 or now.hour >= 20
        plot_dicts = []
        for p in self.plots:
            type_id = 1
            plant_type = 'tree'
            asset_prefix = p.get('asset_prefix') or ''
            if asset_prefix:
                parts = asset_prefix.split(':')
                plant_type = parts[0] if parts else 'tree'
                type_id = int(parts[1]) if len(parts) > 1 else 1

            is_watered = False
            if p.get('last_watered'):
                lw = p['last_watered']
                if lw.tzinfo is None:
                    lw = lw.replace(tzinfo=timezone.utc)
                water_interval = p.get('water_interval_hours') or 4
                hours_since_water = (now - lw).total_seconds() / 3600
                is_watered = hours_since_water < water_interval

            timer_text = None
            timer_color = (255, 255, 255)

            if p['dead']:
                pass
            elif not p['seed_id']:
                pass
            elif (p['growth_stage'] or 0) >= 5:
                timer_text = str(_p('farm:status:ready', 'READY!'))
                timer_color = (255, 215, 0)
            elif not is_watered and p['seed_id']:
                timer_text = str(_p('farm:status:dry', 'DRY!'))
                timer_color = (255, 100, 80)
            elif p['seed_id']:
                pts = p.get('growth_points') or 0
                pts_needed = p.get('growth_points_needed') or 100
                current_stage = p['growth_stage'] or 1
                pts_per_stage = pts_needed / 5.0
                next_stage_pts = current_stage * pts_per_stage
                remaining = max(0, next_stage_pts - pts)
                timer_text = f"{int(pts)}/{int(pts_needed)}"
                timer_color = (200, 230, 255)

            plot_dicts.append({
                'plot_num': p['plot_id'],
                'seed_id': p['seed_id'],
                'growth_stage': p['growth_stage'] or 0,
                'dead': p['dead'],
                'plant_type': plant_type,
                'type_id': type_id,
                'is_watered': is_watered,
                'asset_prefix': asset_prefix,
                'timer_text': timer_text,
                'timer_color': timer_color,
                'rarity': p.get('rarity') or 'COMMON',
            })
        # --- AI-MODIFIED (2026-04-13) ---
        # Purpose: Pass the user's active gameboy skin to the farm view so it matches the pet card
        return FarmState(plots=plot_dicts, is_night=is_night,
                          just_watered=just_watered,
                          gameboy_skin=self._cached_pet_state.gameboy_skin if self._cached_pet_state else "gameboy/frames/gameboy-basic-01.png",
                          pet_state=self._cached_pet_state)
        # --- END AI-MODIFIED ---
    # --- END AI-REPLACED ---

    # --- AI-REPLACED (2026-03-15) ---
    # Reason: Activity-driven progress display with points, investment, farm load
    # What the new code does better: Shows growth points progress, gold invested, farm load indicator
    # --- Original code (commented out for rollback) ---
    # def _plot_status(self, p):
    #     ... basic stage/5 bar, no points or investment info ...
    # def make_embed(self):
    #     ... time-based growth footer with DEV_GROWTH_SPEED ...
    # --- End original code ---
    # --- AI-MODIFIED (2026-03-15) ---
    # --- AI-REPLACED (2026-03-16) ---
    # Reason: Use custom coin/trophy emojis in plot status
    # What the new code does better: Shows pixel-art coin/trophy icons
    # --- Original code (commented out for rollback) ---
    # def _plot_status(self, p) -> str:
    #     from .gameplay import RARITY_EMOJI, RARITY_GOLD_MULTIPLIER
    #     if p['dead']:
    #         return "\U0001F480 Dead"
    #     if not p['seed_id']:
    #         return "\u2B1C Empty"
    #     name = p.get('seed_name') or 'Plant'
    #     rarity = p.get('rarity') or 'COMMON'
    #     r_emoji = RARITY_EMOJI.get(rarity, '')
    #     r_prefix = f"{r_emoji} " if r_emoji else ""
    #     r_tag = f"[{rarity}] " if rarity != 'COMMON' else ""
    #     stage = p['growth_stage'] or 0
    #     if stage >= 5:
    #         base_gold = p.get('harvest_gold') or 20
    #         gold_mult = RARITY_GOLD_MULTIPLIER.get(rarity, 1.0)
    #         harvest_gold = int(base_gold * gold_mult)
    #         return f"\U0001F31F {r_prefix}{r_tag}{name} - **HARVEST!** (+{harvest_gold}G)"
    #     pts = p.get('growth_points') or 0
    #     pts_needed = p.get('growth_points_needed') or 100
    #     bar_filled = "\u2588" * stage
    #     bar_empty = "\u2591" * (5 - stage)
    #     invested = p.get('gold_invested') or 0
    #     return f"\U0001F331 {r_prefix}{r_tag}{name} [{bar_filled}{bar_empty}] {int(pts)}/{int(pts_needed)} pts ({invested}G)"
    # --- End original code ---
    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: Include TIER_HARVEST_GOLD_BONUS in displayed harvest gold
    def _plot_status(self, p) -> str:
        from .gameplay import RARITY_EMOJI, RARITY_GOLD_MULTIPLIER, TIER_HARVEST_GOLD_BONUS
        e_trophy = _lg_emoji('lg_trophy', '\U0001F3C6')
        dead_lbl = str(_p('farm:status:dead', 'Dead'))
        empty_lbl = str(_p('farm:status:empty', 'Empty'))
        harvest_badge = str(_p('farm:plot|harvest_badge', 'HARVEST!'))
        pts_lbl = str(_p('farm:plot|pts_label', 'pts'))
        if p['dead']:
            return f"{_lg_emoji('lg_sick', chr(0x1F480))} {dead_lbl}"
        if not p['seed_id']:
            return f"\u2B1C {empty_lbl}"
        name = p.get('seed_name') or 'Plant'
        rarity = p.get('rarity') or 'COMMON'
        r_emoji = RARITY_EMOJI.get(rarity, '')
        r_prefix = f"{r_emoji} " if r_emoji else ""
        r_tag = f"[{rarity}] " if rarity != 'COMMON' else ""
        stage = p['growth_stage'] or 0
        if stage >= 5:
            base_gold = p.get('harvest_gold') or 20
            gold_mult = RARITY_GOLD_MULTIPLIER.get(rarity, 1.0)
            tier_bonus = 1.0 + TIER_HARVEST_GOLD_BONUS.get(self.user_tier, 0.0)
            harvest_gold = int(base_gold * gold_mult * tier_bonus)
            return f"{e_trophy} {r_prefix}{r_tag}{name} - **{harvest_badge}** (+{harvest_gold}G)"

        pts = p.get('growth_points') or 0
        pts_needed = p.get('growth_points_needed') or 100
        bar_filled = "\u2588" * stage
        bar_empty = "\u2591" * (5 - stage)
        invested = p.get('gold_invested') or 0
        return (
            f"\U0001F331 {r_prefix}{r_tag}{name} [{bar_filled}{bar_empty}] "
            f"{int(pts)}/{int(pts_needed)} {pts_lbl} ({invested}G)"
        )
    # --- END AI-REPLACED ---
    # --- END AI-MODIFIED ---

    def _growth_bar(self, stage: int) -> str:
        filled = "\u2588" * stage
        empty = "\u2591" * (5 - stage)
        return f"[{filled}{empty}]"

    def make_embed(self) -> discord.Embed:
        pet_name = self.cog._last_pet_name or str(_p('pet:fallback_name', 'Leo'))
        embed = discord.Embed(
            title=str(_p('embed:farm|title', "\U0001F33F {pet}'s Farm")).format(pet=pet_name),
            color=discord.Color.green()
        )
        now = datetime.now(timezone.utc)

        active = [p for p in self.plots if p['seed_id'] and not p['dead'] and p['growth_stage'] < 5]
        active_count = len(active)
        planted = sum(1 for p in self.plots if p['seed_id'] and not p['dead'])
        harvestable = sum(1 for p in self.plots if p.get('growth_stage', 0) >= 5 and not p['dead'] and p['seed_id'])
        dead_count = sum(1 for p in self.plots if p['dead'])
        empty_count = sum(1 for p in self.plots if not p['seed_id'] and not p['dead'])
        total_invested = sum(p.get('gold_invested') or 0 for p in self.plots if p['seed_id'] and not p['dead'])

        dry = 0
        for p in self.plots:
            if p['seed_id'] and not p['dead'] and p.get('last_watered'):
                lw = p['last_watered']
                if lw.tzinfo is None:
                    lw = lw.replace(tzinfo=timezone.utc)
                wi = p.get('water_interval_hours') or 4
                if (now - lw).total_seconds() / 3600 >= wi:
                    dry += 1

        if active_count >= 10:
            load_emoji = "\U0001F534"
            load_label = str(_p('embed:farm|load:heavy', 'HEAVY'))
        elif active_count >= 5:
            load_emoji = "\U0001F7E1"
            load_label = str(_p('embed:farm|load:medium', 'Medium'))
        elif active_count >= 1:
            load_emoji = "\U0001F7E2"
            load_label = str(_p('embed:farm|load:light', 'Light'))
        else:
            load_emoji = "\u2B1C"
            load_label = str(_p('embed:farm|load:empty', 'Empty'))

        # --- AI-MODIFIED (2026-03-15) ---
        # Purpose: Show rarity breakdown in farm header
        rarity_counts = {}
        for p in self.plots:
            if p['seed_id'] and not p['dead'] and p['growth_stage'] < 5:
                r = p.get('rarity') or 'COMMON'
                rarity_counts[r] = rarity_counts.get(r, 0) + 1
        # --- END AI-MODIFIED ---

        header = str(_p(
            'embed:farm|header:load_line',
            '{emoji} **Farm Load: {load}** \u2014 {active}/15 growing'
        )).format(emoji=load_emoji, load=load_label, active=active_count)
        if rarity_counts and any(r != 'COMMON' for r in rarity_counts):
            parts = []
            for r in ('LEGENDARY', 'EPIC', 'RARE', 'UNCOMMON', 'COMMON'):
                if r in rarity_counts:
                    parts.append(str(_p(
                        'embed:farm|rarity:count',
                        '{count}\u00d7 {rarity}'
                    )).format(count=rarity_counts[r], rarity=r.title()))
            if parts:
                header += f" ({', '.join(parts)})"
        # --- AI-MODIFIED (2026-03-16) ---
        # Purpose: Use custom coin emoji for invested gold
        header += str(_p(
            'embed:farm|header:invested',
            '{coin} **Invested:** {gold}G across {planted} plants'
        )).format(
            coin=_lg_emoji('lg_coin', chr(0x1F4B0)),
            gold=total_invested,
            planted=planted,
        )
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-04-03) ---
        # Purpose: Fix ETA calculation -- was using old hardcoded constants (1.0 voice, 1.5 water)
        #   instead of actual values (GROWTH_PER_VOICE_MINUTE=3.0, WATER_BOOST=2.0), showing 4x too slow
        # --- Original code (commented out for rollback) ---
        # if active_count > 0:
        #     avg_pts_needed = sum(p.get('growth_points_needed') or 100 for p in active) / active_count
        #     msgs_per_plot = avg_pts_needed / max(0.01, (2.0 / active_count) * 1.5)
        #     vc_min_per_plot = avg_pts_needed / max(0.01, (1.0 / active_count) * 1.5)
        #     vc_display = f"{int(vc_min_per_plot)}m" if vc_min_per_plot < 60 else f"{vc_min_per_plot / 60:.1f}h"
        #     header += str(_p(
        #         'embed:farm|header:grow_estimate',
        #         '\n\U0001F4CA **To fully grow (watered):** ~{msgs} msgs or ~{vc} VC per plant'
        #     )).format(msgs=int(msgs_per_plot), vc=vc_display)
        #     if active_count >= 5:
        #         solo_msgs = avg_pts_needed / (2.0 * 1.5)
        #         header += str(_p(
        #             'embed:farm|header:solo_hint',
        #             '\n\u26A0\uFE0F With 1 plant this would only take ~{msgs} msgs!'
        #         )).format(msgs=int(solo_msgs))
        # --- End original code ---
        if active_count > 0:
            from .gameplay import GROWTH_PER_VOICE_MINUTE, GROWTH_PER_TEXT_MESSAGE, WATER_BOOST
            avg_remaining = sum(
                max(0, (p.get('growth_points_needed') or 100) - (p.get('growth_points') or 0))
                for p in active
            ) / active_count
            watered_msg_rate = (GROWTH_PER_TEXT_MESSAGE / active_count) * WATER_BOOST
            watered_vc_rate = (GROWTH_PER_VOICE_MINUTE / active_count) * WATER_BOOST
            msgs_per_plot = avg_remaining / max(0.01, watered_msg_rate)
            vc_min_per_plot = avg_remaining / max(0.01, watered_vc_rate)
            vc_display = f"{int(vc_min_per_plot)}m" if vc_min_per_plot < 60 else f"{vc_min_per_plot / 60:.1f}h"
            header += str(_p(
                'embed:farm|header:grow_estimate',
                '\n\U0001F4CA **To finish growing (watered):** ~{msgs} msgs or ~{vc} VC per plant'
            )).format(msgs=int(msgs_per_plot), vc=vc_display)
            if active_count >= 5:
                solo_msgs = avg_remaining / max(0.01, GROWTH_PER_TEXT_MESSAGE * WATER_BOOST)
                header += str(_p(
                    'embed:farm|header:solo_hint',
                    '\n\u26A0\uFE0F With 1 plant this would only take ~{msgs} msgs!'
                )).format(msgs=int(solo_msgs))
        # --- END AI-MODIFIED ---

        status_parts = []
        if harvestable:
            status_parts.append(str(_p(
                'embed:farm|status:ready_line',
                '\U0001F31F **{n}** ready!'
            )).format(n=harvestable))
        if dry:
            status_parts.append(str(_p(
                'embed:farm|status:thirsty',
                '\U0001F4A7 **{n}** thirsty'
            )).format(n=dry))
        if dead_count:
            status_parts.append(str(_p(
                'embed:farm|status:dead_line',
                '\U0001F480 **{n}** dead'
            )).format(n=dead_count))
        if empty_count:
            status_parts.append(str(_p(
                'embed:farm|status:empty_line',
                '\u2B1C **{n}** empty'
            )).format(n=empty_count))
        if status_parts:
            sep = str(_p('embed:farm|status:bullet_sep', '  \u2022  '))
            header += "\n" + sep.join(status_parts)

        embed.description = header

        plot_lines = []
        for p in self.plots:
            idx = p['plot_id'] + 1
            line = f"`{idx:2d}.` {self._plot_status(p)}"
            plot_lines.append(line)

        col1 = "\n".join(plot_lines[:8])
        col2 = "\n".join(plot_lines[8:])
        embed.add_field(
            name=str(_p('embed:farm|field:plots1|name', 'Plots 1-8')),
            value=col1 or "\u200b", inline=True)
        embed.add_field(
            name=str(_p('embed:farm|field:plots2|name', 'Plots 9-15')),
            value=col2 or "\u200b", inline=True)

        hints = []
        if harvestable:
            hints.append(str(_p(
                'embed:farm|hint:harvest',
                '\U0001F33E Harvest **{n}** plants for Gold!'
            )).format(n=harvestable))
        if dry:
            hints.append(str(_p(
                'embed:farm|hint:water',
                '\U0001F4A7 **{n}** plants need water or they\'ll die!'
            )).format(n=dry))
        if active_count == 0 and empty_count > 0:
            hints.append(str(_p(
                'embed:farm|hint:start',
                '\U0001F331 Plant seeds to start growing! Be active in VC or chat to grow them.'
            )))
        elif active_count >= 10:
            hints.append(str(_p(
                'embed:farm|hint:heavy',
                '\U0001F525 Heavy load! Growth is spread very thin. Consider harvesting some before planting more.'
            )))
        elif active_count > 0:
            hints.append(str(_p(
                'embed:farm|hint:growth',
                '\U0001F3A4 Voice chat & messages grow your plants. Water them for 1.5x boost!'
            )))
        if hints:
            embed.add_field(name="\u200b", value="\n".join(hints), inline=False)

        embed.set_footer(text=str(_p(
            'embed:farm|footer',
            'Growth splits across all plants | More plants = slower each | Water = 1.5x boost'
        )))
        return embed
    # --- END AI-REPLACED ---

    # --- AI-MODIFIED (2026-03-15) ---
    # Purpose: Support fullscreen toggle and water animation
    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: Send farm image as standalone attachment (not in embed) for higher quality display
    async def show_farm(self, interaction: discord.Interaction, edit: bool = True,
                        just_watered: bool = False):
        if self._cached_pet_state is None:
            pet = await self.cog._get_or_create_pet(self.user_id)
            pet = await self.cog._apply_decay(pet)
            self._cached_pet_state = await self.cog._build_pet_state(pet, self.guild)
        state = self._build_farm_state(just_watered=just_watered)
        if self.fullscreen:
            gif_bytes = await asyncio.to_thread(render_farm_fullscreen, state)
        else:
            gif_bytes = await asyncio.to_thread(render_farm_frame, state)
        file = discord.File(BytesIO(gif_bytes), filename="farm.gif")
        embed = self.make_embed()
        self.refresh_buttons()
        # --- AI-MODIFIED (2026-03-17) ---
        # Purpose: Append artist attribution note to farm content
        farm_content = (embed.description or "") + str(_p(
            'embed:farm|artist_note',
            '\n\n-# *All LionGotchi art is hand-drawn by real humans \u2014 '
            '1,000+ items over 12 months of work, not AI. '
            'Subscriptions & gems support our artists.*'
        ))
        # --- END AI-MODIFIED ---
        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Handle deferred interactions to prevent Unknown Interaction (10062) timeouts
        if not interaction.response.is_done():
            await interaction.response.defer()
        if edit:
            await interaction.edit_original_response(content=farm_content, embed=None, attachments=[file], view=self)
        else:
            await interaction.followup.send(content=farm_content, file=file, view=self)
        # --- END AI-MODIFIED ---
    # --- END AI-MODIFIED ---

    def refresh_buttons(self):
        self.clear_items()

        has_planted = any(p['seed_id'] and not p['dead'] for p in self.plots)
        has_harvestable = any(p.get('growth_stage', 0) >= 5 and p['seed_id'] and not p['dead'] for p in self.plots)
        has_dead = any(p['dead'] for p in self.plots)
        has_empty = any(not p['seed_id'] and not p['dead'] for p in self.plots)

        if has_planted:
            water_btn = discord.ui.Button(
                label=_p('ui:farm|button:water|label', 'Water All'),
                emoji="\U0001F4A7",
                style=discord.ButtonStyle.blurple, row=0)
            water_btn.callback = self.water_all
            self.add_item(water_btn)

        if has_harvestable:
            harvest_btn = discord.ui.Button(
                label=_p('ui:farm|button:harvest|label', 'Harvest All'),
                emoji="\U0001F33E",
                style=discord.ButtonStyle.green, row=0)
            harvest_btn.callback = self.harvest_all
            self.add_item(harvest_btn)

        if has_dead:
            clear_btn = discord.ui.Button(
                label=_p('ui:farm|button:clear_dead|label', 'Clear Dead'),
                emoji="\U0001F480",
                style=discord.ButtonStyle.red, row=0)
            clear_btn.callback = self.clear_dead
            self.add_item(clear_btn)

        # --- AI-MODIFIED (2026-03-15) ---
        # Purpose: Remove Plant button for uprooting growing plants with 50% gold refund
        has_removable = any(
            p['seed_id'] and not p['dead'] and (p.get('growth_stage') or 0) < 5
            for p in self.plots
        )
        if has_removable:
            remove_btn = discord.ui.Button(
                label=_p('ui:farm|button:remove|label', 'Remove Plant'),
                emoji="\u2702\uFE0F",
                style=discord.ButtonStyle.grey, row=0
            )
            remove_btn.callback = self._on_remove_pressed
            self.add_item(remove_btn)
        # --- END AI-MODIFIED ---

        if has_empty:
            empty_plots = [p for p in self.plots if not p['seed_id'] and not p['dead']]
            options = [
                discord.SelectOption(
                    label=str(_p('ui:farm|select:plot|label', 'Plot {num}')).format(
                        num=p['plot_id'] + 1),
                    value=str(p['plot_id']),
                    description=str(_p('ui:farm|select:plot|desc', 'Empty plot'))
                ) for p in empty_plots[:25]
            ]
            plot_select = discord.ui.Select(
                placeholder=_p('ui:farm|select:plot|placeholder', 'Select an empty plot to plant...'),
                options=options, row=1
            )
            plot_select.callback = self._on_plot_selected
            self.add_item(plot_select)

        # --- AI-MODIFIED (2026-03-15) ---
        # Purpose: Add fullscreen toggle button to farm view
        toggle_label = (
            f"\U0001F3AE {str(_p('ui:farm|button:gameboy|label', 'Gameboy'))}"
            if self.fullscreen
            else f"\U0001F4FA {str(_p('ui:farm|button:fullscreen|label', 'Full Screen'))}"
        )
        toggle_btn = discord.ui.Button(
            label=toggle_label,
            style=discord.ButtonStyle.blurple if self.fullscreen else discord.ButtonStyle.grey,
            row=3
        )

        async def _toggle_farm_view(interaction: discord.Interaction):
            await interaction.response.defer()
            new_mode = not self.fullscreen
            await _db_exec(self.cog.bot,
                "UPDATE lg_pets SET fullscreen_mode = %s WHERE userid = %s",
                new_mode, self.user_id)
            self.fullscreen = new_mode
            await self.show_farm(interaction)

        toggle_btn.callback = _toggle_farm_view
        self.add_item(toggle_btn)
        # --- END AI-MODIFIED ---

        back_btn = discord.ui.Button(
            label=_p('ui:farm|button:back|label', 'Back to Pet'),
            emoji="\u2B05",
            style=discord.ButtonStyle.grey, row=3)
        back_btn.callback = self.go_back
        self.add_item(back_btn)

        # --- AI-MODIFIED (2026-03-19) ---
        if hasattr(self, '_vote_btn'):
            self.add_item(self._vote_btn)
        # --- END AI-MODIFIED ---

    # --- AI-REPLACED (2026-03-15) ---
    # Reason: Show seed cost/harvest in dropdown, charge gold on planting
    # What the new code does better: Investment mechanic -- planting costs gold, tracks gold_invested
    # --- Original code (commented out for rollback) ---
    # async def _on_plot_selected(self, interaction):
    #     ... fetched seeds without cost info, no gold charge ...
    # --- End original code ---
    async def _on_plot_selected(self, interaction: discord.Interaction):
        plot_id = int(interaction.data['values'][0])
        seeds = await _db_fetch(self.cog.bot,
            "SELECT seed_id, name, plant_type, plant_cost, harvest_gold, growth_points_needed FROM lg_farm_seeds ORDER BY plant_cost"
        ) or []
        if not seeds:
            await interaction.response.send_message(
                str(_p('error:farm|no_seeds', 'No seed types available!')),
                ephemeral=True)
            return

        gold_rows = await _db_fetch(self.cog.bot,
            "SELECT gold FROM user_config WHERE userid = %s", self.user_id)
        user_gold = gold_rows[0]['gold'] if gold_rows else 0

        # --- AI-MODIFIED (2026-03-17) ---
        # Purpose: Show discounted seed cost for premium users in dropdown
        from .gameplay import TIER_SEED_DISCOUNT
        user_tier, _ = await self.cog._get_premium_context(
            self.user_id, self.guild.id if self.guild else None)
        discount = TIER_SEED_DISCOUNT.get(user_tier, 0.0)

        def _display_cost(base):
            discounted = max(1, int(base * (1.0 - discount)))
            if discount > 0:
                return f"{discounted}G (-{int(discount*100)}%)"
            return f"{base}G"

        options = [
            discord.SelectOption(
                label=s['name'],
                value=str(s['seed_id']),
                description=str(_p(
                    'ui:farm|select:seed|option_desc',
                    'Cost: {cost} | Harvest: {hg}G | {pts} pts'
                )).format(
                    cost=_display_cost(s['plant_cost'] or 10),
                    hg=s['harvest_gold'],
                    pts=s['growth_points_needed'],
                )
            ) for s in seeds[:25]
        ]
        # --- END AI-MODIFIED ---
        view = discord.ui.View(timeout=60)
        seed_select = discord.ui.Select(
            placeholder=_p('ui:farm|select:seed|placeholder', 'Choose a seed to plant...'),
            options=options, row=0)

        async def on_seed_chosen(seed_interaction: discord.Interaction):
            seed_id = int(seed_interaction.data['values'][0])
            chosen = next((s for s in seeds if s['seed_id'] == seed_id), None)
            if not chosen:
                await seed_interaction.response.send_message(
                    str(_p('error:farm|seed_not_found', 'Seed not found!')),
                    ephemeral=True)
                return

            # --- AI-MODIFIED (2026-03-16) ---
            # Purpose: Get user premium tier for farm planting cost calculations
            user_tier, server_premium = await self.cog._get_premium_context(
                self.user_id, self.guild.id if self.guild else None)
            # --- END AI-MODIFIED ---

            # --- AI-MODIFIED (2026-03-17) ---
            # Purpose: Apply TIER_SEED_DISCOUNT for premium users (was defined but never used)
            from .gameplay import TIER_SEED_DISCOUNT
            base_cost = chosen['plant_cost'] or 10
            discount = TIER_SEED_DISCOUNT.get(user_tier, 0.0)
            cost = max(1, int(base_cost * (1.0 - discount)))
            # --- END AI-MODIFIED ---
            fresh_gold = await _db_fetch(self.cog.bot,
                "SELECT gold FROM user_config WHERE userid = %s", self.user_id)
            current_gold = fresh_gold[0]['gold'] if fresh_gold else 0
            if current_gold < cost:
                await seed_interaction.response.send_message(
                    str(_p(
                        'error:farm|not_enough_gold',
                        '\u274C Not enough gold! You need **{need}G** but only have **{have}G**.'
                    )).format(need=cost, have=current_gold),
                    ephemeral=True)
                return

            # --- AI-MODIFIED (2026-03-16) ---
            # Purpose: Roll seed rarity on planting and show reveal with tier-adjusted harvest value
            from .gameplay import roll_seed_rarity, RARITY_GOLD_MULTIPLIER, RARITY_EMOJI, TIER_HARVEST_GOLD_BONUS
            rarity = roll_seed_rarity()

            await seed_interaction.response.defer()
            now = datetime.now(timezone.utc)
            await _db_exec(self.cog.bot,
                "UPDATE user_config SET gold = gold - %s WHERE userid = %s",
                cost, self.user_id)
            await _db_exec(self.cog.bot,
                """INSERT INTO lg_gold_transactions (transaction_type, actorid, to_account, amount, description)
                   VALUES (%s, %s, %s, %s, %s)""",
                'FARM_PLANT', self.user_id, self.user_id, -cost, f'Planted {chosen["name"]}')
            await _db_exec(self.cog.bot,
                """UPDATE lg_user_farm SET seed_id=%s, planted_at=%s, last_watered=%s,
                   growth_stage=1, dead=false, growth_points=0, gold_invested=%s,
                   voice_minutes_earned=0, messages_earned=0, rarity=%s
                   WHERE userid=%s AND plot_id=%s""",
                seed_id, now, now, cost, rarity, self.user_id, plot_id)
            await self.load_farm()
            await self.show_farm(seed_interaction)

            rarity_messages = {
                'RARE': str(_p(
                    'farm:plant|rare',
                    '\u2764\uFE0F You found **Rare** seeds for **{name}**! They glow with a red aura.'
                )).format(name=chosen['name']),
                'EPIC': str(_p(
                    'farm:plant|epic',
                    '\U0001F451 You found **Epic** seeds for **{name}**! A golden light shines from the soil!'
                )).format(name=chosen['name']),
                'LEGENDARY': str(_p(
                    'farm:plant|legendary',
                    '\u2B50 You found **Legendary** seeds for **{name}**! Take great care \u2014 these have a much higher chance of dropping rare craft items!'
                )).format(name=chosen['name']),
            }
            msg = rarity_messages.get(rarity)
            if not msg and rarity == 'UNCOMMON':
                msg = str(_p(
                    'farm:plant|uncommon',
                    '\U0001F539 Your **{name}** seeds shimmer with an uncommon blue hue.'
                )).format(name=chosen['name'])
            if msg:
                gold_mult = RARITY_GOLD_MULTIPLIER.get(rarity, 1.0)
                tier_bonus = 1.0 + TIER_HARVEST_GOLD_BONUS.get(self.user_tier, 0.0)
                harvest = int((chosen['harvest_gold'] or 10) * gold_mult * tier_bonus)
                msg += str(_p(
                    'farm:plant|harvest_value_line',
                    '\n**Harvest value: {harvest}G** (x{mult})'
                )).format(harvest=harvest, mult=gold_mult)
                try:
                    await seed_interaction.followup.send(msg, ephemeral=True)
                except Exception:
                    pass
            # --- END AI-MODIFIED ---

        seed_select.callback = on_seed_chosen
        view.add_item(seed_select)
        cancel_btn = discord.ui.Button(
            label=_p('ui:farm|button:cancel|label', 'Cancel'),
            style=discord.ButtonStyle.grey, row=1)
        cancel_btn.callback = lambda i: self.show_farm(i)
        view.add_item(cancel_btn)

        # --- AI-MODIFIED (2026-03-16) ---
        # Purpose: Use custom coin emoji in planting embed
        embed = discord.Embed(
            title=str(_p(
                'embed:farm_plant|title',
                '\U0001F331 Planting on Plot {n}'
            )).format(n=plot_id + 1),
            description=str(_p(
                'embed:farm_plant|desc',
                '{coin} Your gold: **{gold}G**\nChoose a seed from the dropdown below.'
            )).format(
                coin=_lg_emoji('lg_coin', chr(0x1F4B0)),
                gold=user_gold,
            ),
            color=discord.Color.green())
        # --- END AI-MODIFIED ---
        await interaction.response.edit_message(embed=embed, view=view, attachments=[])
    # --- END AI-REPLACED ---

    # --- AI-MODIFIED (2026-03-15) ---
    # Purpose: Trigger water animation when watering
    async def water_all(self, interaction: discord.Interaction):
        await interaction.response.defer()
        now = datetime.now(timezone.utc)
        await _db_exec(self.cog.bot,
            "UPDATE lg_user_farm SET last_watered=%s WHERE userid=%s AND seed_id IS NOT NULL AND dead=false",
            now, self.user_id)
        await self.load_farm()
        await self.show_farm(interaction, just_watered=True)
    # --- END AI-MODIFIED ---

    # --- AI-REPLACED (2026-03-15) ---
    # Reason: Rich harvest summary with investment vs return, activity stats, material drops
    # What the new code does better: Shows net profit, activity breakdown, and material drops per harvest
    # --- Original code (commented out for rollback) ---
    # async def harvest_all(self, interaction):
    #     ... simple gold sum, no investment tracking or summary ...
    # --- End original code ---
    # --- AI-MODIFIED (2026-03-15) ---
    # Purpose: Apply rarity gold multiplier and drop rate modifier on harvest
    # --- AI-MODIFIED (2026-03-17) ---
    # Purpose: Apply equipment bonus + vote boost to harvest gold, pass server_premium to drops,
    #          add bonus breakdown to harvest summary
    async def harvest_all(self, interaction: discord.Interaction):
        await interaction.response.defer()
        from .gameplay import (try_item_drop, ITEM_DROP_CHANCE_HARVEST, RARITY_GOLD_MULTIPLIER,
                               RARITY_DROP_MULTIPLIER, RARITY_EMOJI, TIER_HARVEST_GOLD_BONUS,
                               calc_equipment_bonus, calc_all_bonuses, format_bonus_summary,
                               check_voted_recently_lg, VOTE_LG_GOLD_BOOST)

        # --- AI-MODIFIED (2026-03-21) ---
        # Purpose: Re-fetch plots from DB to prevent double-harvest if already harvested via website
        await self.load_farm()
        # --- END AI-MODIFIED ---

        user_tier, server_premium = await self.cog._get_premium_context(
            self.user_id, self.guild.id if self.guild else None)

        try:
            bonuses = await calc_all_bonuses(self.cog.bot, self.user_id,
                                             user_tier=user_tier, server_premium=server_premium)
        except Exception:
            logger.debug(f"calc_all_bonuses failed for {self.user_id}, using safe defaults")
            bonuses = {'equip_gold': 1.0, 'vote_gold': 1.0}

        total_harvest_gold = 0
        total_invested = 0
        total_voice_min = 0
        total_messages = 0
        harvested = 0
        all_drops = []
        harvest_details = []

        tier_bonus = 1.0 + TIER_HARVEST_GOLD_BONUS.get(user_tier, 0.0)
        equip_gold_mult = bonuses.get('equip_gold', 1.0)
        vote_boost = bonuses.get('vote_gold', 1.0)
        # --- AI-MODIFIED (2026-03-24) ---
        # Purpose: Pass VC Study Streak quality boost + equipment drop bonus to harvest drops
        vc_boost, _vc_tier, _vc_min = self.cog._get_vc_rarity_boost(self.user_id)
        equip_drop_bonus = bonuses.get('equip_drop', 0.0)
        # --- END AI-MODIFIED ---

        for p in self.plots:
            if p['seed_id'] and not p['dead'] and p['growth_stage'] >= 5:
                rarity = p.get('rarity') or 'COMMON'
                base_gold = p['harvest_gold'] or 20
                gold_mult = RARITY_GOLD_MULTIPLIER.get(rarity, 1.0)
                plant_gold = int(base_gold * gold_mult * tier_bonus * equip_gold_mult * vote_boost)
                total_harvest_gold += plant_gold
                total_invested += p.get('gold_invested') or 0
                total_voice_min += p.get('voice_minutes_earned') or 0
                total_messages += p.get('messages_earned') or 0
                harvested += 1

                name = p.get('seed_name') or 'Plant'
                r_emoji = RARITY_EMOJI.get(rarity, '')
                if rarity != 'COMMON':
                    harvest_details.append(str(_p(
                        'embed:harvest|detail:rare',
                        '{r_emoji} **[{rarity}] {name}** \u2014 {gold}G (x{mult})'
                    )).format(
                        r_emoji=r_emoji, rarity=rarity, name=name,
                        gold=plant_gold, mult=gold_mult))
                else:
                    harvest_details.append(str(_p(
                        'embed:harvest|detail:common',
                        '{name} \u2014 {gold}G'
                    )).format(name=name, gold=plant_gold))

                drop_mult = RARITY_DROP_MULTIPLIER.get(rarity, 1.0)
                # --- AI-MODIFIED (2026-03-24) ---
                # Purpose: Pass equipment drop bonus to harvest drop rolls
                drops = await try_item_drop(self.cog.bot, self.user_id, ITEM_DROP_CHANCE_HARVEST,
                                            rarity_multiplier=drop_mult, user_tier=user_tier,
                                            server_premium=server_premium,
                                            quality_boost=vc_boost,
                                            equip_drop_bonus=equip_drop_bonus)
                # --- END AI-MODIFIED ---
                if drops:
                    all_drops.extend(drops)

                await _db_exec(self.cog.bot,
                    """UPDATE lg_user_farm SET seed_id=NULL, planted_at=NULL, last_watered=NULL,
                       growth_stage=0, dead=false, growth_points=0, gold_invested=0,
                       voice_minutes_earned=0, messages_earned=0, rarity='COMMON'
                       WHERE userid=%s AND plot_id=%s""",
                    self.user_id, p['plot_id'])

        if total_harvest_gold > 0:
            await _db_exec(self.cog.bot,
                "UPDATE user_config SET gold=gold+%s WHERE userid=%s", total_harvest_gold, self.user_id)
            await _db_exec(self.cog.bot,
                """INSERT INTO lg_gold_transactions (transaction_type, actorid, to_account, amount, description)
                   VALUES (%s,%s,%s,%s,%s)""",
                'FARM_HARVEST', self.user_id, self.user_id, total_harvest_gold, f'Harvested {harvested} plants')

        await self.load_farm()
        await self.show_farm(interaction)

        if harvested > 0:
            e_coin = _lg_emoji('lg_coin', '\U0001F4B0')
            e_trophy = _lg_emoji('lg_trophy', '\U0001F3C6')
            e_gift = _lg_emoji('lg_giftbox', '\U0001F381')
            net_profit = total_harvest_gold - total_invested
            profit_emoji = e_coin if net_profit > 0 else "\U0001F4C9"

            summary = str(_p(
                'embed:harvest|summary_title',
                '**{trophy} Harvest Summary**\n'
            )).format(trophy=e_trophy)
            summary += str(_p(
                'embed:harvest|summary_rule',
                '\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n'
            ))
            if harvest_details:
                summary += "\n".join(harvest_details) + "\n\n"
            summary += str(_p(
                'embed:harvest|plants_count',
                '\U0001F331 Plants harvested: **{n}**\n'
            )).format(n=harvested)
            summary += str(_p(
                'embed:harvest|invested',
                '\U0001F4B8 Invested: **{g}G**\n'
            )).format(g=total_invested)
            summary += str(_p(
                'embed:harvest|earned',
                '{coin} Earned: **{g}G**\n'
            )).format(coin=e_coin, g=total_harvest_gold)
            profit_sign = '+' if net_profit >= 0 else ''
            summary += str(_p(
                'embed:harvest|net_profit',
                '{emoji} Net profit: **{sign}{g}G**\n\n'
            )).format(emoji=profit_emoji, sign=profit_sign, g=net_profit)

            activity_parts = []
            if total_voice_min > 0:
                activity_parts.append(str(_p(
                    'embed:harvest|activity:voice',
                    '\U0001F3A4 {n} voice min'
                )).format(n=int(total_voice_min)))
            if total_messages > 0:
                activity_parts.append(str(_p(
                    'embed:harvest|activity:messages',
                    '\U0001F4AC {n} messages'
                )).format(n=int(total_messages)))
            if activity_parts:
                summary += str(_p(
                    'embed:harvest|growth_activity',
                    '**Growth activity:** {parts}\n'
                )).format(parts=', '.join(activity_parts))

            if all_drops:
                drop_names = ', '.join(
                    f"**{d['name']}** ({RARITY_LABELS.get(_clean_rarity(d.get('rarity', 'COMMON')), d.get('rarity', 'Common'))})"
                    for d in all_drops
                )
                summary += str(_p(
                    'embed:harvest|bonus_drops',
                    '\n{gift} **Bonus drops:** {names}\n'
                )).format(gift=e_gift, names=drop_names)

            bonus_text = format_bonus_summary(bonuses)
            if bonus_text:
                summary += str(_p(
                    'embed:harvest|active_bonuses',
                    '\n\u2500\u2500\u2500 **Active Bonuses** \u2500\u2500\u2500\n{text}'
                )).format(text=bonus_text)

            try:
                await interaction.followup.send(summary, ephemeral=True)
            except Exception:
                pass
    # --- END AI-MODIFIED ---

    async def clear_dead(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await _db_exec(self.cog.bot,
            """UPDATE lg_user_farm SET seed_id=NULL, planted_at=NULL, last_watered=NULL,
               growth_stage=0, dead=false, growth_points=0, gold_invested=0,
               voice_minutes_earned=0, messages_earned=0, rarity='COMMON'
               WHERE userid=%s AND dead=true""",
            self.user_id)
        await self.load_farm()
        await self.show_farm(interaction)

    # --- AI-MODIFIED (2026-03-17) ---
    # Purpose: Fix uproot to use TIER_UPROOT_REFUND instead of hardcoded 50%
    async def _on_remove_pressed(self, interaction: discord.Interaction):
        from .gameplay import TIER_UPROOT_REFUND, TIER_DISPLAY_NAMES

        removable = [
            p for p in self.plots
            if p['seed_id'] and not p['dead'] and (p.get('growth_stage') or 0) < 5
        ]
        if not removable:
            await interaction.response.send_message(
                str(_p('error:farm|no_plants_remove', 'No plants to remove!')),
                ephemeral=True)
            return

        user_tier, _ = await self.cog._get_premium_context(
            self.user_id, self.guild.id if self.guild else None)
        refund_rate = TIER_UPROOT_REFUND.get(user_tier, 0.5)
        refund_pct = int(refund_rate * 100)

        options = []
        for p in removable:
            name = p.get('seed_name') or 'Plant'
            invested = p.get('gold_invested') or 0
            refund = int(invested * refund_rate)
            pts = int(p.get('growth_points') or 0)
            pts_needed = int(p.get('growth_points_needed') or 100)
            options.append(discord.SelectOption(
                label=str(_p(
                    'ui:farm|select:remove|label',
                    'Plot {num} - {name}'
                )).format(num=p['plot_id'] + 1, name=name),
                value=str(p['plot_id']),
                description=str(_p(
                    'ui:farm|select:remove|option_desc',
                    '{pts}/{pts_needed} pts | Refund: {refund}G ({refund_pct}% of {invested}G)'
                )).format(
                    pts=pts, pts_needed=pts_needed, refund=refund,
                    refund_pct=refund_pct, invested=invested,
                )
            ))

        view = discord.ui.View(timeout=60)
        remove_select = discord.ui.Select(
            placeholder=_p('ui:farm|select:remove|placeholder', 'Select a plant to remove...'),
            options=options[:25], row=0
        )

        async def on_remove_chosen(select_interaction: discord.Interaction):
            plot_id = int(select_interaction.data['values'][0])
            plot = next((p for p in self.plots if p['plot_id'] == plot_id), None)
            if not plot or not plot['seed_id']:
                await select_interaction.response.send_message(
                    str(_p('error:farm|plot_not_found', 'Plot not found!')),
                    ephemeral=True)
                return

            await select_interaction.response.defer()
            ut, _ = await self.cog._get_premium_context(
                self.user_id, self.guild.id if self.guild else None)
            rr = TIER_UPROOT_REFUND.get(ut, 0.5)
            rr_pct = int(rr * 100)

            name = plot.get('seed_name') or 'Plant'
            invested = plot.get('gold_invested') or 0
            refund = int(invested * rr)

            if refund > 0:
                await _db_exec(self.cog.bot,
                    "UPDATE user_config SET gold = gold + %s WHERE userid = %s",
                    refund, self.user_id)
                await _db_exec(self.cog.bot,
                    """INSERT INTO lg_gold_transactions (transaction_type, actorid, to_account, amount, description)
                       VALUES (%s, %s, %s, %s, %s)""",
                    'FARM_UPROOT', self.user_id, self.user_id, refund,
                    f'Removed {name} ({rr_pct}% refund)')

            await _db_exec(self.cog.bot,
                """UPDATE lg_user_farm SET seed_id=NULL, planted_at=NULL, last_watered=NULL,
                   growth_stage=0, dead=false, growth_points=0, gold_invested=0,
                   voice_minutes_earned=0, messages_earned=0, rarity='COMMON'
                   WHERE userid=%s AND plot_id=%s""",
                self.user_id, plot_id)

            await self.load_farm()
            await self.show_farm(select_interaction)
            try:
                lost = invested - refund
                tier_name = TIER_DISPLAY_NAMES.get(ut)
                tier_note = (
                    str(_p('embed:farm_remove|tier_note', ' ({tier} perk)')).format(tier=tier_name)
                    if tier_name and rr > 0.5 else "")
                lost_suffix = (
                    str(_p('embed:farm_remove|lost_suffix', ' — lost {lost}G')).format(lost=lost)
                    if lost > 0 else "")
                await select_interaction.followup.send(
                    str(_p(
                        'embed:farm_remove|result',
                        '\u2702\uFE0F Removed **{name}** from Plot {plot}. '
                        'Refunded **{refund}G** ({pct}% of {invested}G{tier_note}){lost_suffix}.'
                    )).format(
                        name=name, plot=plot_id + 1, refund=refund,
                        pct=rr_pct, invested=invested, tier_note=tier_note,
                        lost_suffix=lost_suffix,
                    ),
                    ephemeral=True)
            except Exception:
                pass

        remove_select.callback = on_remove_chosen
        view.add_item(remove_select)
        cancel_btn = discord.ui.Button(
            label=_p('ui:farm|button:cancel|label', 'Cancel'),
            style=discord.ButtonStyle.grey, row=1)
        cancel_btn.callback = lambda i: self.show_farm(i)
        view.add_item(cancel_btn)

        refund_desc = str(_p(
            'embed:farm_remove|refund_desc',
            "You'll get back **{pct}%** of what you invested."
        )).format(pct=refund_pct)
        tier_name = TIER_DISPLAY_NAMES.get(user_tier)
        if tier_name and refund_rate > 0.5:
            refund_desc += str(_p(
                'embed:farm_remove|tier_perk_line',
                '\n\U0001F49B {tier} perk: {refund_pct}% refund (base: {base}%)'
            )).format(tier=tier_name, refund_pct=refund_pct, base=50)
        embed = discord.Embed(
            title=str(_p('embed:farm_remove|title', '\u2702\uFE0F Remove a Plant')),
            description=refund_desc,
            color=discord.Color.orange())
        await interaction.response.edit_message(embed=embed, view=view, attachments=[])
    # --- END AI-MODIFIED ---

    async def go_back(self, interaction: discord.Interaction):
        await self.cog._show_pet(interaction, edit=True)


# ============================================================
# Friends System Views
# ============================================================
# --- AI-GENERATED (2026-03-24) ---
# Purpose: Full friend system UI for Discord -- hub, pending requests,
#          friends list, add friend modal, and friend pet care view.

def _calc_max_friends(pet_level: int) -> int:
    return min(20, 10 + (pet_level - 1) // 5)


class FriendsHubView(discord.ui.View):
    """Hub showing friend count, pending count, and navigation buttons."""

    def __init__(self, cog: 'LionGotchiCog', user_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.friend_count = 0
        self.max_friends = 10
        self.pending_count = 0
        self.outgoing_count = 0

    async def load_data(self):
        pet = await _db_fetch(self.cog.bot,
            "SELECT level FROM lg_pets WHERE userid = %s", self.user_id)
        level = pet[0]['level'] if pet else 1
        self.max_friends = _calc_max_friends(level)

        friends = await _db_fetch(self.cog.bot,
            "SELECT COUNT(*) AS cnt FROM lg_friends WHERE userid1 = %s OR userid2 = %s",
            self.user_id, self.user_id)
        self.friend_count = friends[0]['cnt'] if friends else 0

        pending = await _db_fetch(self.cog.bot,
            "SELECT COUNT(*) AS cnt FROM lg_friend_requests WHERE to_userid = %s AND status = 'PENDING'",
            self.user_id)
        self.pending_count = pending[0]['cnt'] if pending else 0

        outgoing = await _db_fetch(self.cog.bot,
            "SELECT COUNT(*) AS cnt FROM lg_friend_requests WHERE from_userid = %s AND status = 'PENDING'",
            self.user_id)
        self.outgoing_count = outgoing[0]['cnt'] if outgoing else 0

        if self.pending_count > 0:
            self.pending_button.style = discord.ButtonStyle.red
            self.pending_button.label = str(_p(
                'ui:friends|button:pending|label', "Pending ({count})")).format(count=self.pending_count)
        else:
            self.pending_button.style = discord.ButtonStyle.grey
            self.pending_button.label = str(_p(
                'ui:friends|button:pending|label', "Pending ({count})")).format(count=0)

    def make_embed(self):
        embed = discord.Embed(
            title=_p('embed:friends_hub|title', "\U0001F465 Friends"),
            description=str(_p(
                'embed:friends_hub|desc',
                "**Friends:** {friend_count}/{max_friends}\n"
                "**Incoming requests:** {pending_count}\n"
                "**Outgoing requests:** {outgoing_count}\n\n"
                "Visit a friend's pet to feed, bathe, or water their farm!"
            )).format(
                friend_count=self.friend_count,
                max_friends=self.max_friends,
                pending_count=self.pending_count,
                outgoing_count=self.outgoing_count,
            ),
            color=0x5865F2
        )
        embed.set_footer(text=_p('embed:friends_hub|footer', "Friend limit increases every 5 pet levels"))
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                _p('error:general|not_your_pet', "Use `/pet` to open your own pet!"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label=_p('ui:friends|button:my_friends|label', "My Friends"), emoji="\U0001F465", style=discord.ButtonStyle.green, row=0)
    async def friends_list_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        view = FriendsListView(self.cog, self.user_id, self.guild_id)
        await view.load_friends()
        await interaction.edit_original_response(
            content=None, embed=view.make_embed(), view=view, attachments=[])

    @discord.ui.button(label=str(_p('ui:friends|button:pending|label', "Pending ({count})")).format(count=0), emoji="\U0001F4E8", style=discord.ButtonStyle.grey, row=0)
    async def pending_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        view = PendingRequestsView(self.cog, self.user_id, self.guild_id)
        await view.load_requests()
        await interaction.edit_original_response(
            content=None, embed=view.make_embed(), view=view, attachments=[])

    @discord.ui.button(label=_p('ui:friends|button:add|label', "Add Friend"), emoji="\u2795", style=discord.ButtonStyle.blurple, row=0)
    async def add_friend_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddFriendModal(self.cog, self.user_id, self.guild_id))

    @discord.ui.button(label=_p('ui:friends|button:back_to_pet|label', "Back to Pet"), emoji="\U0001F519", style=discord.ButtonStyle.grey, row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._show_pet(interaction, edit=True)


class PendingRequestsView(discord.ui.View):
    """Shows incoming pending friend requests with accept/decline."""

    PAGE_SIZE = 5

    def __init__(self, cog: 'LionGotchiCog', user_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.requests = []
        self.page = 0

    async def load_requests(self):
        rows = await _db_fetch(self.cog.bot,
            """SELECT fr.request_id, fr.from_userid, fr.created_at,
                      uc.name AS sender_name, p.pet_name, p.level
               FROM lg_friend_requests fr
               JOIN user_config uc ON uc.userid = fr.from_userid
               LEFT JOIN lg_pets p ON p.userid = fr.from_userid
               WHERE fr.to_userid = %s AND fr.status = 'PENDING'
               ORDER BY fr.created_at DESC""",
            self.user_id)
        self.requests = rows or []
        self._update_buttons()

    def _update_buttons(self):
        total_pages = max(1, (len(self.requests) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.prev_button.disabled = self.page <= 0
        self.next_button.disabled = self.page >= total_pages - 1

        self.request_select.options = []
        start = self.page * self.PAGE_SIZE
        page_items = self.requests[start:start + self.PAGE_SIZE]
        if page_items:
            for req in page_items:
                name = req['sender_name'] or str(req['from_userid'])
                pet_info = f" (Lv.{req['level']} {req['pet_name']})" if req.get('pet_name') else ""
                self.request_select.options.append(
                    discord.SelectOption(
                        label=f"{name}{pet_info}"[:100],
                        value=str(req['request_id']),
                        description=str(_p(
                            'ui:pending|select|description', "Select to accept or decline"))
                    )
                )
            self.request_select.disabled = False
        else:
            self.request_select.options = [
                discord.SelectOption(
                    label=str(_p('ui:pending|select|option:no_requests', "No pending requests")),
                    value="none")
            ]
            self.request_select.disabled = True
        self.accept_button.disabled = True
        self.decline_button.disabled = True
        self._selected_request_id = None

    def make_embed(self):
        if not self.requests:
            return discord.Embed(
                title=_p('embed:pending_requests|title', "\U0001F4E8 Pending Friend Requests"),
                description=_p('embed:pending_requests|desc:empty', "No pending requests!"),
                color=0x5865F2
            )
        total_pages = max(1, (len(self.requests) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        start = self.page * self.PAGE_SIZE
        page_items = self.requests[start:start + self.PAGE_SIZE]

        lines = []
        for req in page_items:
            name = req['sender_name'] or str(req['from_userid'])
            pet_info = f" (Lv.{req['level']} {req['pet_name']})" if req.get('pet_name') else ""
            ts = int(req['created_at'].timestamp()) if req.get('created_at') else 0
            lines.append(f"\u2022 **{name}**{pet_info} \u2014 <t:{ts}:R>")

        embed = discord.Embed(
            title=_p('embed:pending_requests|title', "\U0001F4E8 Pending Friend Requests"),
            description="\n".join(lines),
            color=0x5865F2
        )
        embed.set_footer(text=str(_p(
            'embed:pending_requests|footer',
            "Page {page}/{total_pages} \u2022 {total} total \u2022 Select a request, then Accept or Decline"
        )).format(page=self.page + 1, total_pages=total_pages, total=len(self.requests)))
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                _p('error:general|not_your_pet', "Use `/pet` to open your own pet!"), ephemeral=True)
            return False
        return True

    @discord.ui.select(placeholder=_p('ui:pending|select|placeholder', "Select a request..."), row=0, min_values=1, max_values=1)
    async def request_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        val = select.values[0]
        if val == "none":
            await interaction.response.defer()
            return
        self._selected_request_id = int(val)
        self.accept_button.disabled = False
        self.decline_button.disabled = False
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label=_p('ui:pending|button:accept|label', "Accept"), emoji="\u2705", style=discord.ButtonStyle.green, row=1, disabled=True)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        rid = self._selected_request_id
        if not rid:
            return

        req = await _db_fetch(self.cog.bot,
            "SELECT * FROM lg_friend_requests WHERE request_id = %s AND status = 'PENDING'", rid)
        if not req:
            await interaction.followup.send(
                _p('error:pending|request_gone', "Request no longer exists."), ephemeral=True)
            await self.load_requests()
            await interaction.edit_original_response(embed=self.make_embed(), view=self)
            return

        req = req[0]
        from_id = req['from_userid']

        my_pet = await _db_fetch(self.cog.bot, "SELECT level FROM lg_pets WHERE userid = %s", self.user_id)
        their_pet = await _db_fetch(self.cog.bot, "SELECT level FROM lg_pets WHERE userid = %s", from_id)
        if not my_pet or not their_pet:
            await interaction.followup.send(
                _p('error:friend|no_pet_pair', "One of you no longer has a pet."), ephemeral=True)
            return

        my_max = _calc_max_friends(my_pet[0]['level'])
        their_max = _calc_max_friends(their_pet[0]['level'])

        my_count = await _db_fetch(self.cog.bot,
            "SELECT COUNT(*) AS cnt FROM lg_friends WHERE userid1 = %s OR userid2 = %s",
            self.user_id, self.user_id)
        their_count = await _db_fetch(self.cog.bot,
            "SELECT COUNT(*) AS cnt FROM lg_friends WHERE userid1 = %s OR userid2 = %s",
            from_id, from_id)

        if (my_count[0]['cnt'] if my_count else 0) >= my_max:
            await interaction.followup.send(str(_p(
                'error:friend|limit_reached', "You've reached your friend limit ({max}).")).format(max=my_max),
                ephemeral=True)
            return
        if (their_count[0]['cnt'] if their_count else 0) >= their_max:
            await interaction.followup.send(
                _p('error:friend|sender_limit_reached', "The sender has reached their friend limit."),
                ephemeral=True)
            return

        lower, upper = (self.user_id, from_id) if self.user_id < from_id else (from_id, self.user_id)
        await _db_exec(self.cog.bot,
            "INSERT INTO lg_friends (userid1, userid2) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            lower, upper)
        await _db_exec(self.cog.bot,
            "UPDATE lg_friend_requests SET status = 'ACCEPTED' WHERE request_id = %s", rid)

        name_row = await _db_fetch(self.cog.bot,
            "SELECT name FROM user_config WHERE userid = %s", from_id)
        sender_name = name_row[0]['name'] if name_row and name_row[0].get('name') else str(from_id)
        await interaction.followup.send(str(_p(
            'success:friend|accepted', "\u2705 You are now friends with **{name}**!")).format(name=sender_name),
            ephemeral=True)
        await self.load_requests()
        await interaction.edit_original_response(embed=self.make_embed(), view=self)

    @discord.ui.button(label=_p('ui:pending|button:decline|label', "Decline"), emoji="\u274C", style=discord.ButtonStyle.red, row=1, disabled=True)
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        rid = self._selected_request_id
        if not rid:
            return

        await _db_exec(self.cog.bot,
            "UPDATE lg_friend_requests SET status = 'DECLINED' WHERE request_id = %s AND status = 'PENDING'",
            rid)
        await interaction.followup.send(
            _p('ui:pending|message:declined', "\u274C Request declined."), ephemeral=True)
        await self.load_requests()
        await interaction.edit_original_response(embed=self.make_embed(), view=self)

    @discord.ui.button(label=_p('ui:pending|button:prev|label', "Prev"), style=discord.ButtonStyle.grey, row=2, disabled=True)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label=_p('ui:pending|button:next|label', "Next"), style=discord.ButtonStyle.grey, row=2, disabled=True)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label=_p('ui:friends|button:back|label', "Back"), emoji="\U0001F519", style=discord.ButtonStyle.grey, row=2)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        view = FriendsHubView(self.cog, self.user_id, self.guild_id)
        await view.load_data()
        await interaction.edit_original_response(
            content=None, embed=view.make_embed(), view=view, attachments=[])


class FriendsListView(discord.ui.View):
    """Paginated list of friends with select to visit."""

    PAGE_SIZE = 5

    def __init__(self, cog: 'LionGotchiCog', user_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.friends = []
        self.page = 0

    async def load_friends(self):
        rows = await _db_fetch(self.cog.bot,
            """SELECT f.userid1, f.userid2, f.created_at,
                      uc.name AS friend_name,
                      p.pet_name, p.level, p.food, p.bath, p.sleep
               FROM lg_friends f
               JOIN user_config uc ON uc.userid = CASE
                   WHEN f.userid1 = %s THEN f.userid2 ELSE f.userid1 END
               LEFT JOIN lg_pets p ON p.userid = CASE
                   WHEN f.userid1 = %s THEN f.userid2 ELSE f.userid1 END
               WHERE f.userid1 = %s OR f.userid2 = %s
               ORDER BY p.level DESC NULLS LAST""",
            self.user_id, self.user_id, self.user_id, self.user_id)
        self.friends = []
        for r in (rows or []):
            fid = r['userid2'] if r['userid1'] == self.user_id else r['userid1']
            self.friends.append({**r, 'friend_id': fid})
        self._update_buttons()

    def _update_buttons(self):
        total_pages = max(1, (len(self.friends) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.prev_button.disabled = self.page <= 0
        self.next_button.disabled = self.page >= total_pages - 1

        self.friend_select.options = []
        start = self.page * self.PAGE_SIZE
        page_items = self.friends[start:start + self.PAGE_SIZE]
        if page_items:
            for f in page_items:
                name = f['friend_name'] or str(f['friend_id'])
                pet_info = f" \u2022 Lv.{f['level']} {f['pet_name']}" if f.get('pet_name') else ""
                self.friend_select.options.append(
                    discord.SelectOption(
                        label=f"{name}{pet_info}"[:100],
                        value=str(f['friend_id']),
                        description=str(_p(
                            'ui:friends_list|select|description', "Visit this friend's pet"))
                    )
                )
            self.friend_select.disabled = False
        else:
            self.friend_select.options = [
                discord.SelectOption(
                    label=str(_p('ui:friends_list|select|option:no_friends', "No friends yet")),
                    value="none")
            ]
            self.friend_select.disabled = True

    def make_embed(self):
        if not self.friends:
            return discord.Embed(
                title=_p('embed:friends_list|title', "\U0001F465 My Friends"),
                description=_p(
                    'embed:friends_list|desc:empty',
                    "You don't have any friends yet!\nUse **Add Friend** from the Friends menu to send a request."),
                color=0x5865F2
            )
        total_pages = max(1, (len(self.friends) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        start = self.page * self.PAGE_SIZE
        page_items = self.friends[start:start + self.PAGE_SIZE]

        e_steak = _lg_emoji('lg_steak', '\U0001F356')
        e_soap = _lg_emoji('lg_soap', '\U0001F9FC')
        e_sleep = _lg_emoji('lg_sleep', '\U0001F4A4')

        lines = []
        for f in page_items:
            name = f['friend_name'] or str(f['friend_id'])
            pet_name = f.get('pet_name') or '?'
            level = f.get('level') or 1
            food = f.get('food') or 0
            bath = f.get('bath') or 0
            sleep = f.get('sleep') or 0
            bars = f"{e_steak}`{food}` {e_soap}`{bath}` {e_sleep}`{sleep}`"
            lines.append(f"\u2022 **{name}** \u2014 {pet_name} (Lv.{level})\n  {bars}")

        embed = discord.Embed(
            title=_p('embed:friends_list|title', "\U0001F465 My Friends"),
            description="\n".join(lines),
            color=0x5865F2
        )
        embed.set_footer(text=str(_p(
            'embed:friends_list|footer',
            "Page {page}/{total_pages} \u2022 Select a friend to visit their pet"
        )).format(page=self.page + 1, total_pages=total_pages))
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                _p('error:general|not_your_pet', "Use `/pet` to open your own pet!"), ephemeral=True)
            return False
        return True

    @discord.ui.select(placeholder=_p('ui:friends_list|select|placeholder', "Select a friend to visit..."), row=0, min_values=1, max_values=1)
    async def friend_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        val = select.values[0]
        if val == "none":
            await interaction.response.defer()
            return
        target_id = int(val)
        await interaction.response.defer()
        view = FriendPetView(self.cog, self.user_id, target_id, self.guild_id)
        await view.load_friend()
        embed, file = await view.build_response()
        kwargs = {'content': None, 'embed': embed, 'view': view}
        if file:
            kwargs['attachments'] = [file]
        else:
            kwargs['attachments'] = []
        await interaction.edit_original_response(**kwargs)

    @discord.ui.button(label=_p('ui:friends_list|button:prev|label', "Prev"), style=discord.ButtonStyle.grey, row=1, disabled=True)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label=_p('ui:friends_list|button:next|label', "Next"), style=discord.ButtonStyle.grey, row=1, disabled=True)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label=_p('ui:friends|button:back|label', "Back"), emoji="\U0001F519", style=discord.ButtonStyle.grey, row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        view = FriendsHubView(self.cog, self.user_id, self.guild_id)
        await view.load_data()
        await interaction.edit_original_response(
            content=None, embed=view.make_embed(), view=view, attachments=[])


class AddFriendModal(discord.ui.Modal, title=_p('modal:add_friend|title', "Add Friend")):
    """Modal to send a friend request by Discord username or ID."""

    query_input = discord.ui.TextInput(
        label=_p('modal:add_friend|field:query|label', "Discord username or user ID"),
        placeholder=_p('modal:add_friend|field:query|placeholder', "e.g. CoolUser or 123456789012345678"),
        min_length=1,
        max_length=40,
        required=True,
    )

    def __init__(self, cog: 'LionGotchiCog', user_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        query = self.query_input.value.strip()

        target = None
        if query.isdigit() and len(query) >= 17:
            target = await _db_fetch(self.cog.bot,
                "SELECT userid, name FROM user_config WHERE userid = %s", int(query))
        if not target:
            target = await _db_fetch(self.cog.bot,
                "SELECT userid, name FROM user_config WHERE LOWER(name) = LOWER(%s)", query)
        if not target:
            await interaction.followup.send(str(_p(
                'error:friend|not_found',
                "Could not find user **{query}**. Try their Discord user ID.")).format(query=query),
                ephemeral=True)
            return

        target_id = target[0]['userid']
        target_name = target[0]['name'] or str(target_id)

        if target_id == self.user_id:
            await interaction.followup.send(
                _p('error:friend|self_add', "You can't add yourself!"), ephemeral=True)
            return

        target_pet = await _db_fetch(self.cog.bot,
            "SELECT level FROM lg_pets WHERE userid = %s", target_id)
        if not target_pet:
            await interaction.followup.send(str(_p(
                'error:friend|no_pet', "**{name}** doesn't have a pet yet.")).format(name=target_name),
                ephemeral=True)
            return

        blocked = await _db_fetch(self.cog.bot,
            """SELECT 1 FROM lg_blocks
               WHERE (blocker_userid = %s AND blocked_userid = %s)
                  OR (blocker_userid = %s AND blocked_userid = %s)""",
            target_id, self.user_id, self.user_id, target_id)
        if blocked:
            await interaction.followup.send(
                _p('error:friend|blocked', "Cannot send a friend request to this user."), ephemeral=True)
            return

        lower, upper = (self.user_id, target_id) if self.user_id < target_id else (target_id, self.user_id)
        existing_friend = await _db_fetch(self.cog.bot,
            "SELECT 1 FROM lg_friends WHERE userid1 = %s AND userid2 = %s", lower, upper)
        if existing_friend:
            await interaction.followup.send(
                f"You're already friends with **{target_name}**!", ephemeral=True)
            return

        existing_req = await _db_fetch(self.cog.bot,
            """SELECT 1 FROM lg_friend_requests
               WHERE ((from_userid = %s AND to_userid = %s) OR (from_userid = %s AND to_userid = %s))
                 AND status = 'PENDING'""",
            self.user_id, target_id, target_id, self.user_id)
        if existing_req:
            await interaction.followup.send(
                f"A pending request already exists between you and **{target_name}**.", ephemeral=True)
            return

        my_pet = await _db_fetch(self.cog.bot, "SELECT level FROM lg_pets WHERE userid = %s", self.user_id)
        if not my_pet:
            await interaction.followup.send("You need a pet first! Use `/pet`.", ephemeral=True)
            return

        my_max = _calc_max_friends(my_pet[0]['level'])
        my_count = await _db_fetch(self.cog.bot,
            "SELECT COUNT(*) AS cnt FROM lg_friends WHERE userid1 = %s OR userid2 = %s",
            self.user_id, self.user_id)
        if (my_count[0]['cnt'] if my_count else 0) >= my_max:
            await interaction.followup.send(
                f"You've reached your friend limit ({my_max}).", ephemeral=True)
            return

        their_max = _calc_max_friends(target_pet[0]['level'])
        their_count = await _db_fetch(self.cog.bot,
            "SELECT COUNT(*) AS cnt FROM lg_friends WHERE userid1 = %s OR userid2 = %s",
            target_id, target_id)
        if (their_count[0]['cnt'] if their_count else 0) >= their_max:
            await interaction.followup.send(
                f"**{target_name}** has reached their friend limit.", ephemeral=True)
            return

        # --- AI-MODIFIED (2026-03-24) ---
        # Purpose: Rate limit friend requests to 10 per 24 hours per sender
        RATE_LIMIT = 10
        recent = await _db_fetch(self.cog.bot,
            """SELECT COUNT(*) AS cnt FROM lg_friend_requests
               WHERE from_userid = %s AND created_at >= NOW() - INTERVAL '24 hours'""",
            self.user_id)
        if recent and recent[0]['cnt'] >= RATE_LIMIT:
            await interaction.followup.send(str(_p(
                'error:friend|rate_limited',
                "You can only send {limit} friend requests per day. Try again later.")).format(limit=RATE_LIMIT),
                ephemeral=True)
            return
        # --- END AI-MODIFIED ---

        await _db_exec(self.cog.bot,
            """INSERT INTO lg_friend_requests (from_userid, to_userid, status)
               VALUES (%s, %s, 'PENDING')
               ON CONFLICT (from_userid, to_userid) DO UPDATE SET status = 'PENDING'""",
            self.user_id, target_id)

        await interaction.followup.send(str(_p(
            'success:friend|request_sent', "\U0001F4E8 Friend request sent to **{name}**!")).format(name=target_name),
            ephemeral=True)


class FriendPetView(discord.ui.View):
    """View a friend's pet with care buttons and farm watering."""

    def __init__(self, cog: 'LionGotchiCog', user_id: int, target_id: int, guild_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.target_id = target_id
        self.guild_id = guild_id
        self.target_name = "Friend"
        self.target_pet_name = "Leo"
        self.target_level = 1
        self.target_food = 0
        self.target_bath = 0
        self.target_sleep = 0
        self.today_fed = False
        self.today_bathed = False
        self.today_slept = False
        self.today_watered_plots = set()
        self.farm_plots = []
        self._pet_state = None

    async def load_friend(self):
        config = await _db_fetch(self.cog.bot,
            "SELECT name FROM user_config WHERE userid = %s", self.target_id)
        self.target_name = config[0]['name'] if config else str(self.target_id)

        pet = await _db_fetch(self.cog.bot,
            """SELECT pet_name, level, food, bath, sleep, expression,
                      active_gameboy_skin_id, active_room_id, xp
               FROM lg_pets WHERE userid = %s""", self.target_id)
        if pet:
            p = pet[0]
            self.target_pet_name = p['pet_name'] or 'Leo'
            self.target_level = p['level'] or 1
            self.target_food = p['food'] or 0
            self.target_bath = p['bath'] or 0
            self.target_sleep = p['sleep'] or 0

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        interactions = await _db_fetch(self.cog.bot,
            """SELECT interaction_type, plot_id FROM lg_friend_interactions
               WHERE actor_userid = %s AND target_userid = %s AND created_at >= %s""",
            self.user_id, self.target_id, today_start)
        for row in (interactions or []):
            t = row['interaction_type']
            if t == 'FEED':
                self.today_fed = True
            elif t == 'BATHE':
                self.today_bathed = True
            elif t == 'SLEEP':
                self.today_slept = True
            elif t == 'WATER' and row.get('plot_id') is not None:
                self.today_watered_plots.add(row['plot_id'])

        self.farm_plots = await _db_fetch(self.cog.bot,
            """SELECT plot_id, seed_id, growth_stage, dead
               FROM lg_user_farm WHERE userid = %s AND seed_id IS NOT NULL
               ORDER BY plot_id""",
            self.target_id) or []

        self.feed_button.disabled = self.today_fed
        self.bathe_button.disabled = self.today_bathed
        self.sleep_button.disabled = self.today_slept
        if self.today_fed:
            self.feed_button.style = discord.ButtonStyle.grey
        if self.today_bathed:
            self.bathe_button.style = discord.ButtonStyle.grey
        if self.today_slept:
            self.sleep_button.style = discord.ButtonStyle.grey

        plantable = [p for p in self.farm_plots if not p['dead']]
        unwaterable = all(p['plot_id'] in self.today_watered_plots for p in plantable) if plantable else True
        self.water_all_button.disabled = (not plantable) or unwaterable

        try:
            pet_obj = await self.cog.data.Pet.fetch(self.target_id)
            if pet_obj:
                self._pet_state = await self.cog._build_pet_state(pet_obj, None)
        except Exception:
            logger.exception("Failed to build pet state for friend %s", self.target_id)

    async def build_response(self):
        e_steak = _lg_emoji('lg_steak', '\U0001F356')
        e_soap = _lg_emoji('lg_soap', '\U0001F9FC')
        e_sleep_e = _lg_emoji('lg_sleep', '\U0001F4A4')

        bar_food = "+" * self.target_food + "-" * (8 - self.target_food)
        bar_bath = "+" * self.target_bath + "-" * (8 - self.target_bath)
        bar_sleep = "+" * self.target_sleep + "-" * (8 - self.target_sleep)

        mood = calc_mood(self.target_food, self.target_bath, self.target_sleep)
        mood_label = MOOD_LABELS.get(mood, 'Okay')
        mood_emoji = MOOD_EMOJI.get(mood_label, '\U0001F610')

        fed_mark = " \u2705" if self.today_fed else ""
        bathed_mark = " \u2705" if self.today_bathed else ""
        slept_mark = " \u2705" if self.today_slept else ""

        care_reset = str(_p(
            'embed:friend_pet|care_reset', "-# Care actions reset daily at midnight UTC"))

        farm_line = ""
        if self.farm_plots:
            watered = len(self.today_watered_plots)
            total = len([p for p in self.farm_plots if not p['dead']])
            farm_line = str(_p(
                'embed:friend_pet|farm_planted', "\n\U0001F33F Farm: **{total}** plots planted")).format(total=total)
            if watered > 0:
                farm_line += str(_p(
                    'embed:friend_pet|farm_watered_suffix', " ({watered} watered today)")).format(watered=watered)

        desc = str(_p(
            'embed:friend_pet|desc',
            "**{pet_name}** \u2014 Level {level}\n"
            "{mood_emoji} Mood: **{mood}**\n\n"
            "{e_steak} Hunger `[{bar_food}]`{fed_mark}\n"
            "{e_soap} Clean `[{bar_bath}]`{bathed_mark}\n"
            "{e_sleep} Energy `[{bar_sleep}]`{slept_mark}"
            "{farm_line}\n\n"
            "{care_reset}"
        )).format(
            pet_name=self.target_pet_name,
            level=self.target_level,
            mood_emoji=mood_emoji,
            mood=mood_label,
            e_steak=e_steak,
            bar_food=bar_food,
            fed_mark=fed_mark,
            e_soap=e_soap,
            bar_bath=bar_bath,
            bathed_mark=bathed_mark,
            e_sleep=e_sleep_e,
            bar_sleep=bar_sleep,
            slept_mark=slept_mark,
            farm_line=farm_line,
            care_reset=care_reset,
        )

        embed = discord.Embed(
            title=str(_p('embed:friend_pet|title', "\U0001F465 {name}'s Pet")).format(name=self.target_name),
            description=desc,
            color=0x57F287
        )

        file = None
        if self._pet_state:
            try:
                gif_bytes = await asyncio.to_thread(render_gameboy_frame, self._pet_state)
                file = discord.File(BytesIO(gif_bytes), filename="friend_pet.gif")
                embed.set_thumbnail(url="attachment://friend_pet.gif")
            except Exception:
                logger.exception("Failed to render friend pet")

        return embed, file

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                _p('error:general|not_your_pet', "Use `/pet` to open your own pet!"), ephemeral=True)
            return False
        return True

    async def _do_care(self, interaction: discord.Interaction, care_type: str):
        await interaction.response.defer()

        lower, upper = (self.user_id, self.target_id) if self.user_id < self.target_id else (self.target_id, self.user_id)
        friendship = await _db_fetch(self.cog.bot,
            "SELECT 1 FROM lg_friends WHERE userid1 = %s AND userid2 = %s", lower, upper)
        if not friendship:
            await interaction.followup.send(
                _p('error:friend|not_friends', "You are not friends with this user."), ephemeral=True)
            return

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        existing = await _db_fetch(self.cog.bot,
            """SELECT 1 FROM lg_friend_interactions
               WHERE actor_userid = %s AND target_userid = %s
                 AND interaction_type = %s AND created_at >= %s""",
            self.user_id, self.target_id, care_type, today_start)
        if existing:
            await interaction.followup.send(str(_p(
                'error:friend_pet|care_used', "You already used {care} on this pet today!")).format(
                    care=care_type.title()),
                ephemeral=True)
            return

        # --- AI-MODIFIED (2026-03-25) ---
        # Purpose: Map care types to actual DB column names (feed->food, bathe->bath)
        care_col_map = {'feed': 'food', 'bathe': 'bath', 'sleep': 'sleep'}
        col = care_col_map.get(care_type.lower(), care_type.lower())
        # --- END AI-MODIFIED ---
        await _db_exec(self.cog.bot,
            f"UPDATE lg_pets SET {col} = LEAST({col} + 2, 8) WHERE userid = %s",
            self.target_id)

        await _db_exec(self.cog.bot,
            """INSERT INTO lg_friend_interactions (actor_userid, target_userid, interaction_type)
               VALUES (%s, %s, %s)""",
            self.user_id, self.target_id, care_type)

        if care_type == 'FEED':
            self.today_fed = True
        elif care_type == 'BATHE':
            self.today_bathed = True
        elif care_type == 'SLEEP':
            self.today_slept = True

        await self.load_friend()
        embed, file = await self.build_response()
        kwargs = {'embed': embed, 'view': self}
        if file:
            kwargs['attachments'] = [file]
        await interaction.edit_original_response(**kwargs)

    @discord.ui.button(label=_p('ui:friend_pet|button:feed|label', "Feed"), emoji="\U0001F356", style=discord.ButtonStyle.green, row=0)
    async def feed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do_care(interaction, 'FEED')

    @discord.ui.button(label=_p('ui:friend_pet|button:bathe|label', "Bathe"), emoji="\U0001F9FC", style=discord.ButtonStyle.blurple, row=0)
    async def bathe_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do_care(interaction, 'BATHE')

    @discord.ui.button(label=_p('ui:friend_pet|button:sleep|label', "Sleep"), emoji="\U0001F4A4", style=discord.ButtonStyle.grey, row=0)
    async def sleep_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do_care(interaction, 'SLEEP')

    @discord.ui.button(label=_p('ui:friend_pet|button:water|label', "Water All"), emoji="\U0001F4A7", style=discord.ButtonStyle.green, row=1)
    async def water_all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        lower, upper = (self.user_id, self.target_id) if self.user_id < self.target_id else (self.target_id, self.user_id)
        friendship = await _db_fetch(self.cog.bot,
            "SELECT 1 FROM lg_friends WHERE userid1 = %s AND userid2 = %s", lower, upper)
        if not friendship:
            await interaction.followup.send(
                _p('error:friend|not_friends', "You are not friends with this user."), ephemeral=True)
            return

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        plots = await _db_fetch(self.cog.bot,
            """SELECT plot_id FROM lg_user_farm
               WHERE userid = %s AND seed_id IS NOT NULL AND dead = false""",
            self.target_id) or []

        watered_count = 0
        for plot in plots:
            pid = plot['plot_id']
            if pid in self.today_watered_plots:
                continue
            existing = await _db_fetch(self.cog.bot,
                """SELECT 1 FROM lg_friend_interactions
                   WHERE actor_userid = %s AND target_userid = %s
                     AND interaction_type = 'WATER' AND plot_id = %s AND created_at >= %s""",
                self.user_id, self.target_id, pid, today_start)
            if existing:
                self.today_watered_plots.add(pid)
                continue

            await _db_exec(self.cog.bot,
                "UPDATE lg_user_farm SET last_watered = NOW() WHERE userid = %s AND plot_id = %s",
                self.target_id, pid)
            await _db_exec(self.cog.bot,
                """INSERT INTO lg_friend_interactions (actor_userid, target_userid, interaction_type, plot_id)
                   VALUES (%s, %s, 'WATER', %s)""",
                self.user_id, self.target_id, pid)
            self.today_watered_plots.add(pid)
            watered_count += 1

        if watered_count > 0:
            xp_gained = watered_count * 5
            await _db_exec(self.cog.bot,
                "UPDATE lg_pets SET xp = xp + %s WHERE userid = %s",
                xp_gained, self.user_id)
            await interaction.followup.send(str(_p(
                'success:friend_pet|watered',
                "\U0001F4A7 Watered **{count}** plots! You gained **{xp} XP**.")).format(
                    count=watered_count, xp=xp_gained),
                ephemeral=True)
        else:
            await interaction.followup.send(
                _p('error:friend_pet|no_plots_water', "No plots left to water today."), ephemeral=True)

        await self.load_friend()
        embed, file = await self.build_response()
        kwargs = {'embed': embed, 'view': self}
        if file:
            kwargs['attachments'] = [file]
        await interaction.edit_original_response(**kwargs)

    @discord.ui.button(label=_p('ui:friends|button:back|label', "Back"), emoji="\U0001F519", style=discord.ButtonStyle.grey, row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        view = FriendsListView(self.cog, self.user_id, self.guild_id)
        await view.load_friends()
        await interaction.edit_original_response(
            content=None, embed=view.make_embed(), view=view, attachments=[])


# --- END AI-GENERATED ---


# ============================================================
# Family Views (button-based GUI, no slash commands)
# ============================================================
# --- AI-GENERATED (2026-03-24) ---
# Purpose: Full family management GUI accessible from PetView's Family button.
#          Mirrors the Friends pattern: Hub -> sub-views -> Back to hub -> Back to pet.

from .family_portrait_renderer import (
    FamilyPortraitState, render_family_portrait, PRESET_THEMES, DEFAULT_THEME,
)

FAMILY_CREATE_COST = 10000
FAMILY_NAME_MIN = 2
FAMILY_NAME_MAX = 32

import json as _json


# --- AI-MODIFIED (2026-03-24) ---
# Purpose: Sync permission defaults with website familyPermissions.ts DEFAULT_PERMISSIONS
def _has_family_permission(role: str, perm_key: str, role_permissions: dict) -> bool:
    """Check if a family role has a specific permission."""
    if role == 'LEADER':
        return True
    defaults = {
        'ADMIN': {
            'edit_settings': True, 'invite_members': True, 'kick_members': True,
            'promote_demote': False, 'withdraw_items': True, 'deposit_items': True,
            'withdraw_gold': True, 'deposit_gold': True, 'plant_farm': True,
            'harvest_farm': True, 'disband': False,
        },
        'MODERATOR': {
            'edit_settings': False, 'invite_members': True, 'kick_members': False,
            'promote_demote': False, 'withdraw_items': True, 'deposit_items': True,
            'withdraw_gold': False, 'deposit_gold': True, 'plant_farm': True,
            'harvest_farm': True, 'disband': False,
        },
        'MEMBER': {
            'edit_settings': False, 'invite_members': False, 'kick_members': False,
            'promote_demote': False, 'withdraw_items': False, 'deposit_items': True,
            'withdraw_gold': False, 'deposit_gold': True, 'plant_farm': True,
            'harvest_farm': True, 'disband': False,
        },
    }
    role_defaults = defaults.get(role, {})
    overrides = role_permissions.get(role, {}) if role_permissions else {}
    merged = {**role_defaults, **overrides}
    return merged.get(perm_key, False)
# --- END AI-MODIFIED ---


# --- AI-MODIFIED (2026-04-23) ---
# Purpose: Confirmation view shown when a user clicks Leave/Disband on the
#   family hub. Prevents accidental leaving (which triggers a 7-day rejoin
#   cooldown). Pressing Yes performs the action via FamilyHubView's
#   _do_leave_or_disband helper; Cancel reloads the original family hub.
class FamilyLeaveConfirmView(discord.ui.View):
    """Yes/Cancel confirmation for leaving or disbanding a family."""

    def __init__(self, cog: 'LionGotchiCog', user_id: int, guild_id: int,
                 family: dict, membership: dict):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.family = family
        self.membership = membership
        self.is_leader = (family.get('leader_userid') == user_id)

        if self.is_leader:
            yes_label = str(_p('ui:family|disband|button:yes|label', 'Yes, Disband'))
        else:
            yes_label = str(_p('ui:family|leave|button:yes|label', 'Yes, Leave'))
        yes_btn = discord.ui.Button(
            label=yes_label, emoji="\U0001F6AA",
            style=discord.ButtonStyle.red, row=0)
        yes_btn.callback = self._yes
        self.add_item(yes_btn)

        cancel_btn = discord.ui.Button(
            label=str(_p('ui:family|leave|button:cancel|label', 'Cancel')),
            style=discord.ButtonStyle.grey, row=0)
        cancel_btn.callback = self._cancel
        self.add_item(cancel_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                str(_p('error:family|use_own_pet', 'Use `/pet` to open your own pet!')),
                ephemeral=True)
            return False
        return True

    def make_embed(self) -> discord.Embed:
        family_name = self.family.get('name') or str(_p(
            'display:family|default_name', 'Family'))
        if self.is_leader:
            title = str(_p(
                'embed:family_disband_confirm|title',
                '\u26A0\uFE0F Disband {name}?',
            )).format(name=family_name)
            description = str(_p(
                'embed:family_disband_confirm|desc',
                "This will **permanently delete** your family and remove all members.\n\n"
                "Bank items and treasury gold will be returned to you.\n\n"
                "**You won't be able to join another family for 7 days.**\n\n"
                "Are you sure you want to disband this family?",
            ))
        else:
            title = str(_p(
                'embed:family_leave_confirm|title',
                '\u26A0\uFE0F Leave {name}?',
            )).format(name=family_name)
            description = str(_p(
                'embed:family_leave_confirm|desc',
                "**You won't be able to join another family for 7 days.**\n\n"
                "Are you sure you want to leave this family?",
            ))
        return discord.Embed(
            title=title, description=description, colour=discord.Colour.red())

    async def _yes(self, interaction: discord.Interaction):
        await interaction.response.defer()
        hub = FamilyHubView(self.cog, self.user_id, self.guild_id)
        hub.family = self.family
        hub.membership = self.membership
        try:
            await hub._do_leave_or_disband(interaction)
        except Exception:
            logger.exception("Failed to %s family %s for user %s",
                             'disband' if self.is_leader else 'leave',
                             self.family.get('family_id'), self.user_id)
            try:
                await interaction.followup.send(
                    str(_p(
                        'error:family|leave_disband_failed',
                        "Something went wrong -- please try again in a moment.",
                    )),
                    ephemeral=True)
            except Exception:
                pass

    async def _cancel(self, interaction: discord.Interaction):
        await interaction.response.defer()
        hub = FamilyHubView(self.cog, self.user_id, self.guild_id)
        await hub.load_data()
        content, file, embed = hub.make_content_and_file()
        kwargs = {'view': hub}
        if file:
            kwargs['content'] = content
            kwargs['embed'] = None
            kwargs['attachments'] = [file]
        else:
            kwargs['content'] = None
            kwargs['embed'] = embed
            kwargs['attachments'] = []
        await interaction.edit_original_response(**kwargs)
# --- END AI-MODIFIED ---


class FamilyHubView(discord.ui.View):
    """Main family hub -- shows portrait if in family, or no-family state."""

    def __init__(self, cog: 'LionGotchiCog', user_id: int, guild_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.family = None
        self.membership = None
        self.pending_count = 0
        self._portrait_bytes = None

    async def load_data(self):
        mem = await _db_fetch(self.cog.bot,
            """SELECT fm.family_id, fm.role::text AS role, f.name, f.level, f.xp, f.gold,
                      f.max_members, f.description, f.icon_url, f.leader_userid,
                      f.role_permissions, f.theme
               FROM lg_family_members fm
               JOIN lg_families f ON f.family_id = fm.family_id
               WHERE fm.userid = %s AND fm.left_at IS NULL""",
            self.user_id)
        if mem:
            self.membership = mem[0]
            self.family = mem[0]

        pending = await _db_fetch(self.cog.bot,
            "SELECT COUNT(*) AS cnt FROM lg_family_invites WHERE to_userid = %s AND status = 'PENDING'",
            self.user_id)
        self.pending_count = pending[0]['cnt'] if pending else 0

        if self.family:
            members = await _db_fetch(self.cog.bot,
                """SELECT fm.userid, fm.role::text AS role, uc.name,
                          p.level, p.food, p.bath, p.sleep, p.expression,
                          p.active_gameboy_skin_id, p.active_room_id, p.xp AS pet_xp
                   FROM lg_family_members fm
                   JOIN user_config uc ON uc.userid = fm.userid
                   LEFT JOIN lg_pets p ON p.userid = fm.userid
                   WHERE fm.family_id = %s AND fm.left_at IS NULL
                   ORDER BY
                       CASE fm.role::text
                           WHEN 'LEADER' THEN 0 WHEN 'ADMIN' THEN 1
                           WHEN 'MODERATOR' THEN 2 ELSE 3
                       END, fm.joined_at""",
                self.family['family_id'])

            member_sprites = []
            for m in (members or []):
                if not m.get('level'):
                    continue
                try:
                    pet_obj = await self.cog.data.Pet.fetch(m['userid'])
                    if pet_obj:
                        ps = await self.cog._build_pet_state(pet_obj, None)
                        member_sprites.append((m['name'] or str(m['userid']), m['role'] or 'MEMBER', ps))
                except Exception:
                    logger.exception("Failed to build pet state for family member %s", m['userid'])

            theme_raw = self.family.get('theme')
            if isinstance(theme_raw, str):
                try:
                    theme_raw = _json.loads(theme_raw)
                except Exception:
                    theme_raw = {}
            theme = theme_raw if isinstance(theme_raw, dict) else {}

            rp_raw = self.family.get('role_permissions')
            if isinstance(rp_raw, str):
                try:
                    rp_raw = _json.loads(rp_raw)
                except Exception:
                    rp_raw = {}

            member_count_rows = await _db_fetch(self.cog.bot,
                "SELECT COUNT(*) AS cnt FROM lg_family_members WHERE family_id = %s AND left_at IS NULL",
                self.family['family_id'])
            member_count = member_count_rows[0]['cnt'] if member_count_rows else len(member_sprites)

            portrait_state = FamilyPortraitState(
                family_name=self.family['name'] or str(_p('display:family|default_name', 'Family')),
                family_level=self.family['level'] or 1,
                family_xp=int(self.family['xp'] or 0),
                family_gold=int(self.family['gold'] or 0),
                member_count=member_count,
                max_members=self.family['max_members'] or 10,
                description=self.family.get('description') or '',
                icon_url=self.family.get('icon_url') or '',
                member_sprites=member_sprites,
                theme=theme,
            )
            try:
                self._portrait_bytes = await asyncio.to_thread(render_family_portrait, portrait_state)
            except Exception:
                logger.exception("Failed to render family portrait")
                self._portrait_bytes = None

        self._rebuild_buttons()

    def _rebuild_buttons(self):
        self.clear_items()
        if self.family:
            members_btn = discord.ui.Button(label=_p('ui:family|button:members|label', 'Members'), emoji="\U0001F465",
                                            style=discord.ButtonStyle.green, row=0)
            members_btn.callback = self._open_members
            self.add_item(members_btn)

            farm_btn = discord.ui.Button(label=_p('ui:family|button:farm|label', 'Farm'), emoji="\U0001F33F",
                                         style=discord.ButtonStyle.green, row=0)
            farm_btn.callback = self._open_farm
            self.add_item(farm_btn)

            theme_btn = discord.ui.Button(label=_p('ui:family|button:theme|label', 'Theme'), emoji="\U0001F3A8",
                                          style=discord.ButtonStyle.grey, row=0)
            theme_btn.callback = self._open_theme
            self.add_item(theme_btn)

            role = (self.membership or {}).get('role', 'MEMBER')
            rp_raw = self.family.get('role_permissions')
            if isinstance(rp_raw, str):
                try:
                    rp_raw = _json.loads(rp_raw)
                except Exception:
                    rp_raw = {}
            rp = rp_raw if isinstance(rp_raw, dict) else {}

            if _has_family_permission(role, 'invite_members', rp):
                invite_btn = discord.ui.Button(label=_p('ui:family|button:invite|label', 'Invite'), emoji="\u2795",
                                               style=discord.ButtonStyle.blurple, row=1)
                invite_btn.callback = self._invite_member
                self.add_item(invite_btn)

            is_leader = (self.family.get('leader_userid') == self.user_id)
            leave_label = (
                _p('ui:family|button:disband|label', 'Disband') if is_leader
                else _p('ui:family|button:leave|label', 'Leave'))
            leave_style = discord.ButtonStyle.red if is_leader else discord.ButtonStyle.grey
            leave_btn = discord.ui.Button(label=leave_label, emoji="\U0001F6AA",
                                          style=leave_style, row=1)
            leave_btn.callback = self._leave_or_disband
            self.add_item(leave_btn)

            self.add_item(discord.ui.Button(
                label=_p('ui:family|button:manage|label', 'Manage'), url=f"{WEBSITE_URL}/pet/family",
                style=discord.ButtonStyle.link, row=1
            ))
        else:
            create_btn = discord.ui.Button(label=_p('ui:family|button:create|label', 'Create Family'), emoji="\U0001F3E0",
                                           style=discord.ButtonStyle.green, row=0)
            create_btn.callback = self._create_family
            self.add_item(create_btn)

            pending_label = str(_p(
                'ui:family|button:invites|label', 'Invites ({count})')).format(count=self.pending_count)
            pending_style = discord.ButtonStyle.red if self.pending_count > 0 else discord.ButtonStyle.grey
            pending_btn = discord.ui.Button(label=pending_label, emoji="\U0001F4E8",
                                            style=pending_style, row=0)
            pending_btn.callback = self._open_invites
            self.add_item(pending_btn)

        back_btn = discord.ui.Button(label=_p('ui:family_hub|button:back_to_pet|label', 'Back to Pet'), emoji="\U0001F519",
                                     style=discord.ButtonStyle.grey, row=2)
        back_btn.callback = self._back_to_pet
        self.add_item(back_btn)

    def make_content_and_file(self):
        if self.family and self._portrait_bytes:
            content = str(_p(
                'embed:family_hub|content:with_portrait',
                '\U0001F3E0 **{name}** \u2014 Your role: **{role}**',
            )).format(
                name=self.family['name'],
                role=(self.membership or {}).get('role', 'MEMBER').capitalize(),
            )
            file = discord.File(BytesIO(self._portrait_bytes), filename="family_portrait.gif")
            return content, file, None
        elif self.family:
            embed = discord.Embed(
                title=str(_p('embed:family_hub|title:with_name', '\U0001F3E0 {name}')).format(
                    name=self.family['name']),
                description=str(_p(
                    'embed:family_hub|desc:stats_no_portrait',
                    '**Level:** {level}  |  **Gold:** {gold}\n**Your role:** {role}\n\n{portrait_fail}',
                )).format(
                    level=self.family['level'],
                    gold=f"{int(self.family['gold'] or 0):,}",
                    role=(self.membership or {}).get('role', 'MEMBER').capitalize(),
                    portrait_fail=str(_p(
                        'embed:family_hub|desc:portrait_fail',
                        '*Portrait failed to render -- try again later*',
                    )),
                ),
                color=0x5865F2,
            )
            return None, None, embed
        else:
            embed = discord.Embed(
                title=str(_p('embed:family_hub|title', '\U0001F3E0 Family')),
                description=str(_p(
                    'embed:family_hub|desc:no_family',
                    "You're not in a family yet!\n\n"
                    'Create one for **{cost}G** or accept a pending invite.\n\n'
                    'Families let you share farms, bank items, pool gold, '
                    "and show off a group portrait of all members' pets!",
                )).format(cost=f'{FAMILY_CREATE_COST:,}'),
                color=0x5865F2,
            )
            if self.pending_count > 0:
                embed.set_footer(text=str(_p(
                    'embed:family_hub|footer:pending_invites',
                    'You have {count} pending invite(s)!',
                )).format(count=self.pending_count))
            return None, None, embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                str(_p('error:family|use_own_pet', 'Use `/pet` to open your own pet!')),
                ephemeral=True)
            return False
        return True

    async def _open_members(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = FamilyMembersView(self.cog, self.user_id, self.guild_id, self.family['family_id'])
        await view.load_members()
        await interaction.edit_original_response(
            content=None, embed=view.make_embed(), view=view, attachments=[])

    async def _open_farm(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = FamilyFarmView(self.cog, self.user_id, self.guild_id, self.family['family_id'])
        await view.load_farm()
        content, file, embed = view.make_response()
        kwargs = {'view': view}
        if file:
            kwargs['content'] = content
            kwargs['embed'] = None
            kwargs['attachments'] = [file]
        else:
            kwargs['content'] = None
            kwargs['embed'] = embed
            kwargs['attachments'] = []
        await interaction.edit_original_response(**kwargs)

    async def _open_theme(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = FamilyThemeView(self.cog, self.user_id, self.guild_id, self.family['family_id'],
                               self.family.get('theme'))
        await interaction.edit_original_response(
            content=None, embed=view.make_embed(), view=view, attachments=[])

    async def _invite_member(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            InviteMemberModal(self.cog, self.user_id, self.guild_id, self.family['family_id'],
                              (self.membership or {}).get('role', 'MEMBER'),
                              self.family.get('role_permissions')))

    # --- AI-REPLACED (2026-03-24) ---
    # Reason: Disband was deleting family without refunding treasury or bank items
    # What the new code does better: Returns bank items to leader's inventory and
    #   refunds treasury gold before deletion, matching website disband.ts behavior
    # --- Original code (commented out for rollback) ---
    # async def _leave_or_disband(self, interaction):
    #     is_leader = (self.family.get('leader_userid') == self.user_id)
    #     if is_leader:
    #         await _db_exec(bot, "UPDATE lg_family_members SET left_at = NOW() WHERE family_id = %s", fid)
    #         await _db_exec(bot, "DELETE FROM lg_families WHERE family_id = %s", fid)
    #     else:
    #         await _db_exec(bot, "UPDATE lg_family_members SET left_at = NOW() WHERE family_id = %s AND userid = %s", fid, uid)
    # --- End original code ---
    # --- AI-MODIFIED (2026-04-23) ---
    # Purpose: Add confirmation prompt before leave/disband so members don't
    #   accidentally leave their family and get stuck on the 7-day rejoin cooldown
    #   (requested by community member Sky). The Leave/Disband button now swaps
    #   the family hub message for a Yes/Cancel confirm view, then performs the
    #   action only after the user confirms.
    # --- Previous code (commented out for rollback) ---
    # async def _leave_or_disband(self, interaction: discord.Interaction):
    #     # Immediate action -- no confirmation. Body now lives in
    #     # _do_leave_or_disband below.
    # --- End previous code ---
    async def _leave_or_disband(self, interaction: discord.Interaction):
        confirm_view = FamilyLeaveConfirmView(
            self.cog, self.user_id, self.guild_id,
            self.family, self.membership)
        embed = confirm_view.make_embed()
        await interaction.response.edit_message(
            content=None, embed=embed, attachments=[], view=confirm_view)

    async def _do_leave_or_disband(self, interaction: discord.Interaction):
        """Perform the actual leave or disband DB ops.

        Called from FamilyLeaveConfirmView after the user confirms. The
        interaction here is the Yes button press, which has already been
        deferred so we can use followup.send for the success message and
        edit_original_response (via _show_pet) to navigate back to the pet.
        """
        is_leader = (self.family.get('leader_userid') == self.user_id)
        fid = self.family['family_id']
        if is_leader:
            bank_items = await _db_fetch(self.cog.bot,
                "SELECT itemid, enhancement_level, quantity, scroll_data "
                "FROM lg_family_bank WHERE family_id = %s", fid)
            for item in (bank_items or []):
                inv_rows = await _db_fetch(self.cog.bot,
                    """INSERT INTO lg_user_inventory (userid, itemid, enhancement_level, quantity, source)
                       VALUES (%s, %s, %s, %s, 'DROP') RETURNING inventoryid""",
                    self.user_id, item['itemid'],
                    item.get('enhancement_level') or 0,
                    item.get('quantity') or 1)
                sd = item.get('scroll_data')
                if inv_rows and sd and isinstance(sd, list):
                    inv_id = inv_rows[0]['inventoryid']
                    for slot in sd:
                        if isinstance(slot, dict) and 'slot_number' in slot:
                            await _db_exec(self.cog.bot,
                                """INSERT INTO lg_enhancement_slots
                                   (inventoryid, slot_number, scroll_itemid, bonus_value)
                                   VALUES (%s, %s, %s, %s)""",
                                inv_id, slot['slot_number'],
                                slot.get('scroll_itemid'),
                                slot.get('bonus_value', 0))

            family_gold = int(self.family.get('gold') or 0)
            if family_gold > 0:
                await _db_exec(self.cog.bot,
                    "UPDATE user_config SET gold = gold + %s WHERE userid = %s",
                    family_gold, self.user_id)

            await _db_exec(self.cog.bot,
                "UPDATE lg_family_members SET left_at = NOW() WHERE family_id = %s", fid)
            await _db_exec(self.cog.bot,
                "DELETE FROM lg_families WHERE family_id = %s", fid)

            refund_parts = []
            if bank_items:
                refund_parts.append(str(_p(
                    'msg:family|disband|refund_items',
                    '{count} item(s) returned to inventory',
                )).format(count=len(bank_items)))
            if family_gold > 0:
                refund_parts.append(str(_p(
                    'msg:family|disband|refund_gold',
                    '**{gold}G** treasury refunded',
                )).format(gold=f'{family_gold:,}'))
            refund_msg = (" | ".join(refund_parts) + "\n") if refund_parts else ""
            await interaction.followup.send(
                str(_p(
                    'msg:family|disband|done',
                    '\U0001F6AA Family **{name}** has been disbanded.\n{refund}',
                )).format(name=self.family['name'], refund=refund_msg),
                ephemeral=True)
        else:
            await _db_exec(self.cog.bot,
                "UPDATE lg_family_members SET left_at = NOW() WHERE family_id = %s AND userid = %s",
                fid, self.user_id)
            await interaction.followup.send(
                str(_p(
                    'msg:family|leave|done',
                    '\U0001F6AA You left **{name}**.',
                )).format(name=self.family['name']),
                ephemeral=True)
        await self.cog._show_pet(interaction, edit=True)
    # --- END AI-MODIFIED ---
    # --- END AI-REPLACED ---

    async def _create_family(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            CreateFamilyModal(self.cog, self.user_id, self.guild_id))

    async def _open_invites(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = FamilyInvitesView(self.cog, self.user_id, self.guild_id)
        await view.load_invites()
        await interaction.edit_original_response(
            content=None, embed=view.make_embed(), view=view, attachments=[])

    async def _back_to_pet(self, interaction: discord.Interaction):
        await self.cog._show_pet(interaction, edit=True)


class CreateFamilyModal(discord.ui.Modal, title=_p('modal:create_family|title', 'Create Family')):
    """Modal to create a new family."""

    family_name_input = discord.ui.TextInput(
        label=_p('modal:create_family|field:name|label', 'Family Name'),
        placeholder=_p('modal:create_family|field:name|placeholder', 'Enter a name (2-32 characters)'),
        min_length=FAMILY_NAME_MIN,
        max_length=FAMILY_NAME_MAX,
    )

    def __init__(self, cog: 'LionGotchiCog', user_id: int, guild_id: int):
        super().__init__()
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id

    # --- AI-REPLACED (2026-04-15) ---
    # Reason: Family creation silently failed -- 8 sequential DB roundtrips ran
    #   before the first interaction response, exceeding Discord's 3-second timeout.
    #   No on_error handler meant exceptions were silently swallowed (user saw nothing).
    #   Gold deduction and family INSERT used separate connections with no transaction,
    #   so partial failures could lose gold without creating the family.
    # What the new code does better:
    #   1. Defers interaction immediately so DB work doesn't race the 3-second timeout
    #   2. Wraps all mutations in a single DB transaction (atomic gold + family creation)
    #   3. Adds on_error handler to report failures instead of swallowing them
    # --- Original code (commented out for rollback) ---
    # async def on_submit(self, interaction):
    #     name = self.family_name_input.value.strip()
    #     # ... validation with interaction.response.send_message (no defer) ...
    #     gold_rows = await _db_fetch(bot, "SELECT gold FROM user_config WHERE userid = %s", uid)
    #     # ... gold/name/membership checks ...
    #     await _db_exec(bot, "UPDATE user_config SET gold = gold - %s ...", cost, uid)      # separate conn
    #     family_rows = await _db_fetch(bot, "INSERT INTO lg_families ... RETURNING ...", n, uid)  # separate conn
    #     await _db_exec(bot, "INSERT INTO lg_family_members ...", fid, uid)                 # separate conn
    #     await _db_exec(bot, "INSERT INTO lg_family_farms ...", fid)                        # separate conn
    #     await _db_exec(bot, "INSERT INTO lg_family_farm_plots ...", fid)                   # separate conn
    #     await interaction.response.send_message(success, ephemeral=True)  # first response after 8 DB calls
    #     hub = FamilyHubView(...); await hub.load_data()
    #     await interaction.edit_original_response(**kwargs)
    # --- End original code ---
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        name = self.family_name_input.value.strip()
        if len(name) < FAMILY_NAME_MIN or len(name) > FAMILY_NAME_MAX:
            await interaction.followup.send(
                str(_p(
                    'error:family|name_length',
                    'Name must be {min}-{max} characters.',
                )).format(min=FAMILY_NAME_MIN, max=FAMILY_NAME_MAX),
                ephemeral=True)
            return

        gold_rows = await _db_fetch(self.cog.bot,
            "SELECT gold FROM user_config WHERE userid = %s", self.user_id)
        gold = gold_rows[0]['gold'] if gold_rows else 0
        if (gold or 0) < FAMILY_CREATE_COST:
            await interaction.followup.send(
                str(_p(
                    'error:family|not_enough_gold',
                    'You need **{need}G** to create a family. You have **{have}G**.',
                )).format(need=f'{FAMILY_CREATE_COST:,}', have=f'{gold or 0:,}'),
                ephemeral=True)
            return

        existing = await _db_fetch(self.cog.bot,
            "SELECT family_id FROM lg_families WHERE LOWER(name) = LOWER(%s)", name)
        if existing:
            await interaction.followup.send(
                str(_p(
                    'error:family|name_taken',
                    'A family named **{name}** already exists. Choose a different name.',
                )).format(name=name),
                ephemeral=True)
            return

        already_in = await _db_fetch(self.cog.bot,
            "SELECT family_id FROM lg_family_members WHERE userid = %s AND left_at IS NULL", self.user_id)
        if already_in:
            await interaction.followup.send(
                str(_p(
                    'error:family|already_in_family',
                    "You're already in a family! Leave first before creating a new one.",
                )),
                ephemeral=True)
            return

        async with self.cog.bot.db.connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    await cur.execute(
                        "UPDATE user_config SET gold = gold - %s WHERE userid = %s",
                        [FAMILY_CREATE_COST, self.user_id])

                    await cur.execute(
                        """INSERT INTO lg_families (name, leader_userid, level, xp, gold,
                                                    max_members, max_farms,
                                                    daily_gold_withdraw_cap,
                                                    role_permissions, theme)
                           VALUES (%s, %s, 1, 0, 0, 10, 1, 10000, '{}', '{}')
                           RETURNING family_id""",
                        [name, self.user_id])
                    family_row = await cur.fetchone()
                    family_id = family_row['family_id']

                    await cur.execute(
                        """INSERT INTO lg_family_members
                               (family_id, userid, role, joined_at, contribution_xp)
                           VALUES (%s, %s, 'LEADER', NOW(), 0)""",
                        [family_id, self.user_id])

                    await cur.execute(
                        """INSERT INTO lg_family_farms (family_id, farm_index, unlocked_at)
                           VALUES (%s, 0, NOW())""",
                        [family_id])

                    await cur.execute(
                        """INSERT INTO lg_family_farm_plots
                               (family_id, farm_index, plot_id)
                           SELECT %s, 0, generate_series(0, 14)""",
                        [family_id])

        await interaction.followup.send(
            str(_p(
                'success:family|created',
                '\U0001F389 Family **{name}** created! You are the Leader.\nCost: **{cost}G**',
            )).format(name=name, cost=f'{FAMILY_CREATE_COST:,}'),
            ephemeral=True)

        try:
            hub = FamilyHubView(self.cog, self.user_id, self.guild_id)
            await hub.load_data()
            content, file, embed = hub.make_content_and_file()
            kwargs = {'view': hub}
            if file:
                kwargs['content'] = content
                kwargs['embed'] = None
                kwargs['attachments'] = [file]
            else:
                kwargs['content'] = None
                kwargs['embed'] = embed
                kwargs['attachments'] = []
            await interaction.edit_original_response(**kwargs)
        except Exception:
            logger.debug("Failed to refresh family hub after creation", exc_info=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logger.exception("Family creation failed for user %s", self.user_id)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    str(_p(
                        'error:family|creation_failed',
                        'Something went wrong creating the family. Please try again.',
                    )),
                    ephemeral=True)
            else:
                await interaction.response.send_message(
                    str(_p(
                        'error:family|creation_failed',
                        'Something went wrong creating the family. Please try again.',
                    )),
                    ephemeral=True)
        except Exception:
            pass
    # --- END AI-REPLACED ---


class FamilyInvitesView(discord.ui.View):
    """Shows pending family invites with accept/decline."""

    PAGE_SIZE = 5

    def __init__(self, cog: 'LionGotchiCog', user_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.invites = []
        self.page = 0
        self.selected_invite_id = None

    async def load_invites(self):
        self.invites = await _db_fetch(self.cog.bot,
            """SELECT fi.invite_id, fi.family_id, fi.from_userid, fi.created_at,
                      f.name AS family_name, f.level AS family_level,
                      uc.name AS from_name
               FROM lg_family_invites fi
               JOIN lg_families f ON f.family_id = fi.family_id
               LEFT JOIN user_config uc ON uc.userid = fi.from_userid
               WHERE fi.to_userid = %s AND fi.status = 'PENDING'
               ORDER BY fi.created_at DESC""",
            self.user_id) or []
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        page_invites = self.invites[self.page * self.PAGE_SIZE:(self.page + 1) * self.PAGE_SIZE]

        if page_invites:
            options = [
                discord.SelectOption(
                    label=str(_p(
                        'ui:family_invites|select:invite|label',
                        '{family_name} (Lv.{level})',
                    )).format(family_name=inv['family_name'], level=inv['family_level'] or 1),
                    description=str(_p(
                        'ui:family_invites|select:invite|desc',
                        'From: {from_name}',
                    )).format(from_name=inv['from_name'] or str(_p(
                        'ui:family_invites|unknown_sender', 'Unknown'))),
                    value=str(inv['invite_id']),
                )
                for inv in page_invites
            ]
            select = discord.ui.Select(
                placeholder=_p('ui:family_invites|select:placeholder', 'Select an invite...'),
                options=options, row=0)
            select.callback = self._on_select
            self.add_item(select)

            accept_btn = discord.ui.Button(label=_p('ui:family_invites|button:accept|label', 'Accept'), emoji="\u2705",
                                           style=discord.ButtonStyle.green, row=1,
                                           disabled=self.selected_invite_id is None)
            accept_btn.callback = self._accept
            self.add_item(accept_btn)

            decline_btn = discord.ui.Button(label=_p('ui:family_invites|button:decline|label', 'Decline'), emoji="\u274C",
                                            style=discord.ButtonStyle.red, row=1,
                                            disabled=self.selected_invite_id is None)
            decline_btn.callback = self._decline
            self.add_item(decline_btn)

        total_pages = max(1, math.ceil(len(self.invites) / self.PAGE_SIZE))
        if total_pages > 1:
            prev_btn = discord.ui.Button(label=_p('ui:family|button:prev|label', 'Prev'), style=discord.ButtonStyle.grey,
                                         row=2, disabled=self.page == 0)
            prev_btn.callback = self._prev
            self.add_item(prev_btn)
            next_btn = discord.ui.Button(label=_p('ui:family|button:next|label', 'Next'), style=discord.ButtonStyle.grey,
                                         row=2, disabled=self.page >= total_pages - 1)
            next_btn.callback = self._next
            self.add_item(next_btn)

        back_btn = discord.ui.Button(label=_p('ui:family|button:back|label', 'Back'), emoji="\U0001F519",
                                     style=discord.ButtonStyle.grey, row=2)
        back_btn.callback = self._back
        self.add_item(back_btn)

    def make_embed(self):
        if not self.invites:
            return discord.Embed(
                title=str(_p('embed:family_invites|title', '\U0001F4E8 Family Invites')),
                description=str(_p('embed:family_invites|desc:empty', 'No pending invites.')),
                color=0x5865F2,
            )
        lines = []
        for inv in self.invites[self.page * self.PAGE_SIZE:(self.page + 1) * self.PAGE_SIZE]:
            lines.append(str(_p(
                'embed:family_invites|line',
                '\u2022 **{family_name}** (Lv.{level}) \u2014 from {from_name}',
            )).format(
                family_name=inv['family_name'],
                level=inv['family_level'] or 1,
                from_name=inv['from_name'] or str(_p('ui:family_invites|unknown_sender', 'Unknown')),
            ))
        total_pages = max(1, math.ceil(len(self.invites) / self.PAGE_SIZE))
        return discord.Embed(
            title=str(_p('embed:family_invites|title', '\U0001F4E8 Family Invites')),
            description="\n".join(lines),
            color=0x5865F2,
        ).set_footer(text=str(_p(
            'embed:family_invites|footer',
            'Page {cur}/{total} \u2022 Select an invite to accept or decline',
        )).format(cur=self.page + 1, total=total_pages))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                str(_p('error:family|use_own_pet', 'Use `/pet` to open your own pet!')),
                ephemeral=True)
            return False
        return True

    async def _on_select(self, interaction: discord.Interaction):
        self.selected_invite_id = int(interaction.data['values'][0])
        self._rebuild()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    # --- AI-REPLACED (2026-03-24) ---
    # Reason: Missing 7-day leave cooldown and member cap checks (website has both)
    # What the new code does better: Enforces cooldown after leaving a family and
    #   checks member count vs level-based max before allowing join
    # --- Original code (commented out for rollback) ---
    # async def _accept(self, interaction):
    #     already = await _db_fetch(bot, "SELECT family_id FROM lg_family_members WHERE userid=%s AND left_at IS NULL", uid)
    #     if already: return "already in family"
    #     inv = await _db_fetch(bot, "SELECT family_id FROM lg_family_invites WHERE invite_id=%s AND status='PENDING'", iid)
    #     family_id = inv[0]['family_id']
    #     await _db_exec(bot, "UPDATE lg_family_invites SET status='ACCEPTED' ...", iid)
    #     await _db_exec(bot, "INSERT INTO lg_family_members ... ON CONFLICT DO UPDATE SET left_at=NULL", fid, uid)
    # --- End original code ---
    async def _accept(self, interaction: discord.Interaction):
        if not self.selected_invite_id:
            return
        already = await _db_fetch(self.cog.bot,
            "SELECT family_id FROM lg_family_members WHERE userid = %s AND left_at IS NULL",
            self.user_id)
        if already:
            await interaction.response.send_message(
                str(_p(
                    'error:family|already_in_family_invite',
                    "You're already in a family! Leave first.",
                )),
                ephemeral=True)
            return

        COOLDOWN_DAYS = 7
        last_left = await _db_fetch(self.cog.bot,
            """SELECT left_at FROM lg_family_members
               WHERE userid = %s AND left_at IS NOT NULL
               ORDER BY left_at DESC LIMIT 1""",
            self.user_id)
        if last_left and last_left[0].get('left_at'):
            left_at = last_left[0]['left_at']
            if left_at.tzinfo is None:
                left_at = left_at.replace(tzinfo=timezone.utc)
            days_since = (datetime.now(timezone.utc) - left_at).total_seconds() / 86400
            if days_since < COOLDOWN_DAYS:
                remaining = int(COOLDOWN_DAYS - days_since) + 1
                await interaction.response.send_message(
                    str(_p(
                        'error:family|cooldown',
                        'You recently left a family. Cooldown: **{days} day(s)** remaining.',
                    )).format(days=remaining),
                    ephemeral=True)
                return

        inv = await _db_fetch(self.cog.bot,
            "SELECT family_id FROM lg_family_invites WHERE invite_id = %s AND status = 'PENDING'",
            self.selected_invite_id)
        if not inv:
            await interaction.response.send_message(
                str(_p('error:invite|not_found', 'Invite no longer valid.')),
                ephemeral=True)
            return

        family_id = inv[0]['family_id']

        fam_info = await _db_fetch(self.cog.bot,
            "SELECT xp, max_members FROM lg_families WHERE family_id = %s", family_id)
        if not fam_info:
            await interaction.response.send_message(
                str(_p('error:invite|family_gone', 'Family no longer exists.')),
                ephemeral=True)
            return
        mem_count = await _db_fetch(self.cog.bot,
            "SELECT COUNT(*) as cnt FROM lg_family_members WHERE family_id = %s AND left_at IS NULL",
            family_id)
        fam_xp = int(fam_info[0].get('xp') or 0)
        fam_level = family_level_from_xp(fam_xp)
        max_mem = max(fam_info[0].get('max_members') or 10, 10 + (fam_level - 1) // 2)
        if (mem_count[0]['cnt'] or 0) >= max_mem:
            await interaction.response.send_message(
                str(_p(
                    'error:family|full',
                    'This family is full! They need to level up to unlock more slots.',
                )),
                ephemeral=True)
            return

        await _db_exec(self.cog.bot,
            "UPDATE lg_family_invites SET status = 'ACCEPTED' WHERE invite_id = %s",
            self.selected_invite_id)
        await _db_exec(self.cog.bot,
            """INSERT INTO lg_family_members (family_id, userid, role, joined_at, contribution_xp)
               VALUES (%s, %s, 'MEMBER', NOW(), 0)
               ON CONFLICT (family_id, userid) DO UPDATE SET left_at = NULL, role = 'MEMBER',
               joined_at = NOW(), contribution_xp = 0""",
            family_id, self.user_id)

        await interaction.response.send_message(
            str(_p('success:family|joined', '\u2705 You joined the family!')),
            ephemeral=True)

        hub = FamilyHubView(self.cog, self.user_id, self.guild_id)
        await hub.load_data()
        content, file, embed = hub.make_content_and_file()
        kwargs = {'view': hub}
        if file:
            kwargs['content'] = content
            kwargs['embed'] = None
            kwargs['attachments'] = [file]
        else:
            kwargs['content'] = None
            kwargs['embed'] = embed
            kwargs['attachments'] = []
        await interaction.edit_original_response(**kwargs)
    # --- END AI-REPLACED ---

    async def _decline(self, interaction: discord.Interaction):
        if not self.selected_invite_id:
            return
        await _db_exec(self.cog.bot,
            "UPDATE lg_family_invites SET status = 'DECLINED' WHERE invite_id = %s",
            self.selected_invite_id)
        self.selected_invite_id = None
        await interaction.response.defer()
        await self.load_invites()
        await interaction.edit_original_response(embed=self.make_embed(), view=self)

    async def _prev(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self.selected_invite_id = None
        self._rebuild()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self.page += 1
        self.selected_invite_id = None
        self._rebuild()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def _back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        hub = FamilyHubView(self.cog, self.user_id, self.guild_id)
        await hub.load_data()
        content, file, embed = hub.make_content_and_file()
        kwargs = {'view': hub}
        if file:
            kwargs['content'] = content
            kwargs['embed'] = None
            kwargs['attachments'] = [file]
        else:
            kwargs['content'] = None
            kwargs['embed'] = embed
            kwargs['attachments'] = []
        await interaction.edit_original_response(**kwargs)


class FamilyMembersView(discord.ui.View):
    """Paginated list of family members. Select opens pet view."""

    PAGE_SIZE = 10

    def __init__(self, cog: 'LionGotchiCog', user_id: int, guild_id: int, family_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.family_id = family_id
        self.members = []
        self.page = 0

    async def load_members(self):
        self.members = await _db_fetch(self.cog.bot,
            """SELECT fm.userid, fm.role::text AS role, fm.contribution_xp,
                      uc.name, p.level, p.pet_name
               FROM lg_family_members fm
               JOIN user_config uc ON uc.userid = fm.userid
               LEFT JOIN lg_pets p ON p.userid = fm.userid
               WHERE fm.family_id = %s AND fm.left_at IS NULL
               ORDER BY
                   CASE fm.role::text
                       WHEN 'LEADER' THEN 0 WHEN 'ADMIN' THEN 1
                       WHEN 'MODERATOR' THEN 2 ELSE 3
                   END, fm.joined_at""",
            self.family_id) or []
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        page_members = self.members[self.page * self.PAGE_SIZE:(self.page + 1) * self.PAGE_SIZE]

        if page_members:
            options = [
                discord.SelectOption(
                    label=str(_p(
                        'ui:family_members|select:member|label',
                        '{display} (Lv.{level})',
                    )).format(display=m['name'] or str(m['userid']), level=m['level'] or 1),
                    description=str(_p(
                        'ui:family_members|select:member|desc',
                        '{role} \u2022 {pet_name}',
                    )).format(
                        role=(m['role'] or 'MEMBER').capitalize(),
                        pet_name=m['pet_name'] or str(_p('display:pet|default_name', 'Leo')),
                    ),
                    value=str(m['userid']),
                )
                for m in page_members
            ]
            select = discord.ui.Select(
                placeholder=_p('ui:family_members|select:placeholder', 'Select a member to view...'),
                options=options, row=0)
            select.callback = self._on_select
            self.add_item(select)

        total_pages = max(1, math.ceil(len(self.members) / self.PAGE_SIZE))
        if total_pages > 1:
            prev_btn = discord.ui.Button(label=_p('ui:family|button:prev|label', 'Prev'), style=discord.ButtonStyle.grey,
                                         row=1, disabled=self.page == 0)
            prev_btn.callback = self._prev
            self.add_item(prev_btn)
            next_btn = discord.ui.Button(label=_p('ui:family|button:next|label', 'Next'), style=discord.ButtonStyle.grey,
                                         row=1, disabled=self.page >= total_pages - 1)
            next_btn.callback = self._next
            self.add_item(next_btn)

        back_btn = discord.ui.Button(label=_p('ui:family|button:back|label', 'Back'), emoji="\U0001F519",
                                     style=discord.ButtonStyle.grey, row=1)
        back_btn.callback = self._back
        self.add_item(back_btn)

    def make_embed(self):
        role_icons = {'LEADER': '\u2654', 'ADMIN': '\u2605', 'MODERATOR': '\u2666', 'MEMBER': '\u2022'}
        lines = []
        start = self.page * self.PAGE_SIZE
        for m in self.members[start:start + self.PAGE_SIZE]:
            icon = role_icons.get(m['role'], '\u2022')
            xp = int(m['contribution_xp'] or 0)
            lines.append(str(_p(
                'embed:family_members|line',
                '{icon} **{display}** \u2014 Lv.{level} \u2022 {role} \u2022 {xp} XP',
            )).format(
                icon=icon,
                display=m['name'] or str(m['userid']),
                level=m['level'] or 1,
                role=(m['role'] or 'MEMBER').capitalize(),
                xp=f'{xp:,}',
            ))
        total_pages = max(1, math.ceil(len(self.members) / self.PAGE_SIZE))
        desc = "\n".join(lines) if lines else str(_p('embed:family_members|desc:empty', 'No members.'))
        return discord.Embed(
            title=str(_p(
                'embed:family_members|title',
                '\U0001F465 Family Members ({count})',
            )).format(count=len(self.members)),
            description=desc,
            color=0x5865F2,
        ).set_footer(text=str(_p(
            'embed:family_members|footer',
            'Page {cur}/{total} \u2022 Select a member to view their pet',
        )).format(cur=self.page + 1, total=total_pages))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                str(_p('error:family|use_own_pet', 'Use `/pet` to open your own pet!')),
                ephemeral=True)
            return False
        return True

    async def _on_select(self, interaction: discord.Interaction):
        target_id = int(interaction.data['values'][0])
        await interaction.response.defer()
        view = FamilyMemberPetView(self.cog, self.user_id, target_id, self.guild_id, self.family_id)
        await view.load_member()
        embed, file = await view.build_response()
        kwargs = {'embed': embed, 'view': view, 'content': None}
        if file:
            kwargs['attachments'] = [file]
        else:
            kwargs['attachments'] = []
        await interaction.edit_original_response(**kwargs)

    async def _prev(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self._rebuild()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self.page += 1
        self._rebuild()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def _back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        hub = FamilyHubView(self.cog, self.user_id, self.guild_id)
        await hub.load_data()
        content, file, embed = hub.make_content_and_file()
        kwargs = {'view': hub}
        if file:
            kwargs['content'] = content
            kwargs['embed'] = None
            kwargs['attachments'] = [file]
        else:
            kwargs['content'] = None
            kwargs['embed'] = embed
            kwargs['attachments'] = []
        await interaction.edit_original_response(**kwargs)


class FamilyMemberPetView(discord.ui.View):
    """View a family member's pet with Gameboy render thumbnail."""

    def __init__(self, cog: 'LionGotchiCog', user_id: int, target_id: int,
                 guild_id: int, family_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.target_id = target_id
        self.guild_id = guild_id
        self.family_id = family_id
        self.target_name = "Member"
        self.target_pet_name = "Leo"
        self.target_level = 1
        self.target_food = 0
        self.target_bath = 0
        self.target_sleep = 0
        self.target_role = "MEMBER"
        self._pet_state = None

    async def load_member(self):
        config = await _db_fetch(self.cog.bot,
            "SELECT name FROM user_config WHERE userid = %s", self.target_id)
        self.target_name = config[0]['name'] if config else str(self.target_id)

        pet = await _db_fetch(self.cog.bot,
            "SELECT pet_name, level, food, bath, sleep FROM lg_pets WHERE userid = %s",
            self.target_id)
        if pet:
            p = pet[0]
            self.target_pet_name = p['pet_name'] or 'Leo'
            self.target_level = p['level'] or 1
            self.target_food = p['food'] or 0
            self.target_bath = p['bath'] or 0
            self.target_sleep = p['sleep'] or 0

        mem = await _db_fetch(self.cog.bot,
            "SELECT role::text AS role FROM lg_family_members WHERE family_id = %s AND userid = %s AND left_at IS NULL",
            self.family_id, self.target_id)
        if mem:
            self.target_role = mem[0]['role'] or 'MEMBER'

        try:
            pet_obj = await self.cog.data.Pet.fetch(self.target_id)
            if pet_obj:
                self._pet_state = await self.cog._build_pet_state(pet_obj, None)
        except Exception:
            logger.exception("Failed to build pet state for family member %s", self.target_id)

    async def build_response(self):
        e_steak = _lg_emoji('lg_steak', '\U0001F356')
        e_soap = _lg_emoji('lg_soap', '\U0001F9FC')
        e_sleep_e = _lg_emoji('lg_sleep', '\U0001F4A4')

        bar_food = "+" * self.target_food + "-" * (8 - self.target_food)
        bar_bath = "+" * self.target_bath + "-" * (8 - self.target_bath)
        bar_sleep = "+" * self.target_sleep + "-" * (8 - self.target_sleep)

        mood = calc_mood(self.target_food, self.target_bath, self.target_sleep)
        mood_label = MOOD_LABELS.get(mood, 'Okay')
        mood_emoji = MOOD_EMOJI.get(mood_label, '\U0001F610')

        role_icons = {'LEADER': '\u2654', 'ADMIN': '\u2605', 'MODERATOR': '\u2666', 'MEMBER': '\u2022'}
        role_icon = role_icons.get(self.target_role, '\u2022')

        embed = discord.Embed(
            title=str(_p(
                'embed:family_member_pet|title',
                "\U0001F3E0 {name}'s Pet",
            )).format(name=self.target_name),
            description=str(_p(
                'embed:family_member_pet|desc',
                '**{pet}** \u2014 Level {level}\n'
                '{role_icon} Family role: **{role}**\n'
                '{mood_emoji} Mood: **{mood}**\n\n'
                '{e_steak} Hunger `[{bar_food}]`\n'
                '{e_soap} Clean `[{bar_bath}]`\n'
                '{e_sleep} Energy `[{bar_sleep}]`',
            )).format(
                pet=self.target_pet_name,
                level=self.target_level,
                role_icon=role_icon,
                role=self.target_role.capitalize(),
                mood_emoji=mood_emoji,
                mood=mood_label,
                e_steak=e_steak,
                bar_food=bar_food,
                e_soap=e_soap,
                bar_bath=bar_bath,
                e_sleep=e_sleep_e,
                bar_sleep=bar_sleep,
            ),
            color=0x57F287,
        )

        file = None
        if self._pet_state:
            try:
                gif_bytes = await asyncio.to_thread(render_gameboy_frame, self._pet_state)
                file = discord.File(BytesIO(gif_bytes), filename="member_pet.gif")
                embed.set_thumbnail(url="attachment://member_pet.gif")
            except Exception:
                logger.exception("Failed to render family member pet")

        return embed, file

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                str(_p('error:family|use_own_pet', 'Use `/pet` to open your own pet!')),
                ephemeral=True)
            return False
        return True

    @discord.ui.button(label=_p('ui:family|button:back|label', 'Back'), emoji="\U0001F519", style=discord.ButtonStyle.grey, row=0)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        view = FamilyMembersView(self.cog, self.user_id, self.guild_id, self.family_id)
        await view.load_members()
        await interaction.edit_original_response(
            content=None, embed=view.make_embed(), view=view, attachments=[])


class FamilyFarmView(discord.ui.View):
    """Read-only view of the family farm with rendered preview."""

    def __init__(self, cog: 'LionGotchiCog', user_id: int, guild_id: int, family_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.family_id = family_id
        self.plots = []
        self._gif_bytes = None
        self._farm_exists = False

    async def load_farm(self):
        farms = await _db_fetch(self.cog.bot,
            "SELECT farm_index FROM lg_family_farms WHERE family_id = %s ORDER BY farm_index LIMIT 1",
            self.family_id)
        if not farms:
            return

        self._farm_exists = True
        farm_index = farms[0]['farm_index']

        # --- AI-MODIFIED (2026-03-24) ---
        # Purpose: Removed s.type_id from query (column never existed in DB).
        # type_id is now derived from asset_prefix, matching the personal farm code.
        self.plots = await _db_fetch(self.cog.bot,
            # --- AI-MODIFIED (2026-03-30) ---
            # Purpose: Include water_interval_hours for correct watered visualization
            """SELECT fp.plot_id, fp.seed_id, fp.growth_stage, fp.dead, fp.rarity,
                      fp.last_watered, fp.planted_at,
                      s.plant_type::text AS plant_type, s.asset_prefix,
                      s.water_interval_hours
               FROM lg_family_farm_plots fp
               LEFT JOIN lg_farm_seeds s ON s.seed_id = fp.seed_id
               WHERE fp.family_id = %s AND fp.farm_index = %s
               ORDER BY fp.plot_id""",
            # --- END AI-MODIFIED ---
            self.family_id, farm_index) or []
        # --- END AI-MODIFIED ---

        plot_dicts = []
        from datetime import timezone as tz
        now = datetime.now(tz.utc)
        for p in self.plots:
            # --- AI-REPLACED (2026-03-30) ---
            # Reason: Date-only comparison gave wrong soil colors; use water_interval_hours like personal farm
            # What the new code does better: Matches the actual growth engine logic
            # --- Original code (commented out for rollback) ---
            # is_watered = False
            # if p.get('last_watered'):
            #     lw = p['last_watered']
            #     if hasattr(lw, 'date'):
            #         is_watered = lw.date() == now.date()
            # --- End original code ---
            is_watered = False
            if p.get('last_watered'):
                lw = p['last_watered']
                if lw.tzinfo is None:
                    lw = lw.replace(tzinfo=tz.utc)
                water_interval = p.get('water_interval_hours') or 4
                hours_since = (now - lw).total_seconds() / 3600
                is_watered = hours_since < water_interval
            # --- END AI-REPLACED ---

            # --- AI-MODIFIED (2026-03-24) ---
            # Purpose: Derive type_id from asset_prefix (matching personal farm logic)
            type_id = 1
            plant_type = p.get('plant_type') or 'tree'
            asset_prefix = p.get('asset_prefix') or ''
            if asset_prefix:
                parts = asset_prefix.split(':')
                plant_type = parts[0] if parts else 'tree'
                type_id = int(parts[1]) if len(parts) > 1 else 1
            # --- END AI-MODIFIED ---

            plot_dicts.append({
                'plot_num': p['plot_id'],
                'seed_id': p['seed_id'],
                'growth_stage': p['growth_stage'] or 0,
                'dead': p.get('dead', False),
                'rarity': p.get('rarity') or 'COMMON',
                'plant_type': plant_type,
                'type_id': type_id,
                'asset_prefix': asset_prefix,
                'is_watered': is_watered,
                'timer_text': None,
                'timer_color': (255, 255, 255),
            })

        try:
            pet = await self.cog._get_or_create_pet(self.user_id)
            pet_state = await self.cog._build_pet_state(pet, None)
        except Exception:
            pet_state = None

        state = FarmState(
            plots=plot_dicts,
            is_night=False,
            just_watered=False,
            gameboy_skin=pet_state.gameboy_skin if pet_state else "gameboy/frames/gameboy-basic-01.png",
            pet_state=pet_state,
        )
        try:
            self._gif_bytes = await asyncio.to_thread(render_farm_frame, state)
        except Exception:
            logger.exception("Failed to render family farm")
        self._add_nav_buttons()

    def make_response(self):
        if not self._farm_exists:
            embed = discord.Embed(
                title=str(_p('embed:family_farm|title', '\U0001F33F Family Farm')),
                description=str(_p(
                    'embed:family_farm|desc:no_farm',
                    'No farm unlocked yet.\n\nManage your family farm on the website!',
                )),
                color=0x5865F2,
            )
            return None, None, embed

        planted = sum(1 for p in self.plots if p.get('seed_id') and not p.get('dead'))
        content = str(_p(
            'embed:family_farm|content:preview',
            '\U0001F33F **Family Farm** \u2014 {planted} plots planted\n\n'
            '-# *Read-only preview. Manage the farm on the website.*',
        )).format(planted=planted)

        file = None
        if self._gif_bytes:
            file = discord.File(BytesIO(self._gif_bytes), filename="family_farm.gif")

        return content, file, None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                str(_p('error:family|use_own_pet', 'Use `/pet` to open your own pet!')),
                ephemeral=True)
            return False
        return True

    def _add_nav_buttons(self):
        self.add_item(discord.ui.Button(
            label=_p('ui:family|button:manage|label', 'Manage'), url=f"{WEBSITE_URL}/pet/family",
            style=discord.ButtonStyle.link, row=0
        ))
        back_btn = discord.ui.Button(label=_p('ui:family|button:back|label', 'Back'), emoji="\U0001F519",
                                     style=discord.ButtonStyle.grey, row=0)
        back_btn.callback = self._go_back
        self.add_item(back_btn)

    async def _go_back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        hub = FamilyHubView(self.cog, self.user_id, self.guild_id)
        await hub.load_data()
        content, file, embed = hub.make_content_and_file()
        kwargs = {'view': hub}
        if file:
            kwargs['content'] = content
            kwargs['embed'] = None
            kwargs['attachments'] = [file]
        else:
            kwargs['content'] = None
            kwargs['embed'] = embed
            kwargs['attachments'] = []
        await interaction.edit_original_response(**kwargs)


class FamilyThemeView(discord.ui.View):
    """Select or customize family theme."""

    def __init__(self, cog: 'LionGotchiCog', user_id: int, guild_id: int,
                 family_id: int, current_theme=None):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.family_id = family_id
        self.current_theme = current_theme if isinstance(current_theme, dict) else {}

        theme_options = [
            discord.SelectOption(
                label=_p('ui:theme|preset:default|label', 'Default'),
                value="default",
                description=_p('ui:theme|preset:default|desc', 'Classic blurple & gold')),
            discord.SelectOption(
                label=_p('ui:theme|preset:royal_gold|label', 'Royal Gold'),
                value="royal_gold",
                description=_p('ui:theme|preset:royal_gold|desc', 'Dark bg, gold accents')),
            discord.SelectOption(
                label=_p('ui:theme|preset:ocean_blue|label', 'Ocean Blue'),
                value="ocean_blue",
                description=_p('ui:theme|preset:ocean_blue|desc', 'Deep navy, aqua glow')),
            discord.SelectOption(
                label=_p('ui:theme|preset:forest_green|label', 'Forest Green'),
                value="forest_green",
                description=_p('ui:theme|preset:forest_green|desc', 'Dark green, emerald')),
            discord.SelectOption(
                label=_p('ui:theme|preset:midnight|label', 'Midnight'),
                value="midnight",
                description=_p('ui:theme|preset:midnight|desc', 'Near-black, silver & purple')),
            discord.SelectOption(
                label=_p('ui:theme|preset:sunset|label', 'Sunset'),
                value="sunset",
                description=_p('ui:theme|preset:sunset|desc', 'Warm orange-purple gradient')),
            discord.SelectOption(
                label=_p('ui:theme|preset:cherry_blossom|label', 'Cherry Blossom'),
                value="cherry_blossom",
                description=_p('ui:theme|preset:cherry_blossom|desc', 'Dark pink, magenta')),
        ]
        select = discord.ui.Select(
            placeholder=_p('ui:theme|select:theme|placeholder', 'Choose a theme...'),
            options=theme_options, row=0)
        select.callback = self._on_theme_select
        self.add_item(select)

        back_btn = discord.ui.Button(label=_p('ui:family|button:back|label', 'Back'), emoji="\U0001F519",
                                     style=discord.ButtonStyle.grey, row=1)
        back_btn.callback = self._back
        self.add_item(back_btn)

    def make_embed(self):
        return discord.Embed(
            title=str(_p('embed:family_theme|title', '\U0001F3A8 Family Theme')),
            description=str(_p(
                'embed:family_theme|desc',
                'Choose a preset theme for your family portrait!\n\n'
                'The theme changes the background colors, borders, '
                'glow effects, and accent colors of your family card.',
            )),
            color=0x5865F2,
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                str(_p('error:family|use_own_pet', 'Use `/pet` to open your own pet!')),
                ephemeral=True)
            return False
        return True

    async def _on_theme_select(self, interaction: discord.Interaction):
        theme_key = interaction.data['values'][0]
        if theme_key == 'default':
            theme = {}
        else:
            theme = PRESET_THEMES.get(theme_key, {})

        await _db_exec(self.cog.bot,
            "UPDATE lg_families SET theme = %s WHERE family_id = %s",
            _json.dumps(theme), self.family_id)

        theme_display_names = {
            'default': str(_p('ui:theme|preset:default|label', 'Default')),
            'royal_gold': str(_p('ui:theme|preset:royal_gold|label', 'Royal Gold')),
            'ocean_blue': str(_p('ui:theme|preset:ocean_blue|label', 'Ocean Blue')),
            'forest_green': str(_p('ui:theme|preset:forest_green|label', 'Forest Green')),
            'midnight': str(_p('ui:theme|preset:midnight|label', 'Midnight')),
            'sunset': str(_p('ui:theme|preset:sunset|label', 'Sunset')),
            'cherry_blossom': str(_p('ui:theme|preset:cherry_blossom|label', 'Cherry Blossom')),
        }
        display_name = theme_display_names.get(
            theme_key, theme_key.replace('_', ' ').title())

        await interaction.response.send_message(
            str(_p(
                'msg:theme|set',
                '\U0001F3A8 Theme set to **{name}**!',
            )).format(name=display_name),
            ephemeral=True)

        hub = FamilyHubView(self.cog, self.user_id, self.guild_id)
        await hub.load_data()
        content, file, embed = hub.make_content_and_file()
        kwargs = {'view': hub}
        if file:
            kwargs['content'] = content
            kwargs['embed'] = None
            kwargs['attachments'] = [file]
        else:
            kwargs['content'] = None
            kwargs['embed'] = embed
            kwargs['attachments'] = []
        await interaction.edit_original_response(**kwargs)

    async def _back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        hub = FamilyHubView(self.cog, self.user_id, self.guild_id)
        await hub.load_data()
        content, file, embed = hub.make_content_and_file()
        kwargs = {'view': hub}
        if file:
            kwargs['content'] = content
            kwargs['embed'] = None
            kwargs['attachments'] = [file]
        else:
            kwargs['content'] = None
            kwargs['embed'] = embed
            kwargs['attachments'] = []
        await interaction.edit_original_response(**kwargs)


class InviteMemberModal(discord.ui.Modal, title=_p('modal:invite_member|title', 'Invite to Family')):
    """Modal to invite a user to the family."""

    target_input = discord.ui.TextInput(
        label=_p('modal:invite_member|field:target|label', 'Discord username or user ID'),
        placeholder=_p(
            'modal:invite_member|field:target|placeholder',
            'Enter their LionGotchi username or numeric ID',
        ),
        min_length=1,
        max_length=40,
    )

    def __init__(self, cog: 'LionGotchiCog', user_id: int, guild_id: int,
                 family_id: int, role: str, role_permissions):
        super().__init__()
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.family_id = family_id
        self.role = role
        self.role_permissions = role_permissions if isinstance(role_permissions, dict) else {}

    async def on_submit(self, interaction: discord.Interaction):
        target_str = self.target_input.value.strip()

        if target_str.isdigit():
            target_rows = await _db_fetch(self.cog.bot,
                "SELECT userid, name FROM user_config WHERE userid = %s", int(target_str))
        else:
            target_rows = await _db_fetch(self.cog.bot,
                "SELECT userid, name FROM user_config WHERE LOWER(name) = LOWER(%s)", target_str)

        if not target_rows:
            await interaction.response.send_message(
                str(_p(
                    'error:invite|not_found',
                    'Could not find user **{target}**.',
                )).format(target=target_str),
                ephemeral=True)
            return

        target_id = target_rows[0]['userid']
        target_name = target_rows[0]['name'] or str(target_id)

        if target_id == self.user_id:
            await interaction.response.send_message(
                str(_p('error:invite|self_invite', "You can't invite yourself!")),
                ephemeral=True)
            return

        has_pet = await _db_fetch(self.cog.bot,
            "SELECT userid FROM lg_pets WHERE userid = %s", target_id)
        if not has_pet:
            await interaction.response.send_message(
                str(_p(
                    'error:invite|no_pet',
                    "**{name}** doesn't have a LionGotchi pet yet.",
                )).format(name=target_name),
                ephemeral=True)
            return

        already_in = await _db_fetch(self.cog.bot,
            "SELECT family_id FROM lg_family_members WHERE userid = %s AND left_at IS NULL",
            target_id)
        if already_in:
            await interaction.response.send_message(
                str(_p(
                    'error:invite|target_in_family',
                    '**{name}** is already in a family.',
                )).format(name=target_name),
                ephemeral=True)
            return

        pending = await _db_fetch(self.cog.bot,
            "SELECT invite_id FROM lg_family_invites WHERE family_id = %s AND to_userid = %s AND status = 'PENDING'",
            self.family_id, target_id)
        if pending:
            await interaction.response.send_message(
                str(_p(
                    'error:invite|duplicate_pending',
                    '**{name}** already has a pending invite from your family.',
                )).format(name=target_name),
                ephemeral=True)
            return

        # --- AI-MODIFIED (2026-03-24) ---
        # Purpose: Rate limit invites to prevent spam (max 10 per hour per inviter)
        INVITE_RATE_MAX = 10
        INVITE_RATE_WINDOW = 3600
        now = _time.time()
        inviter_times = self.cog._invite_send_rate.get(self.user_id, [])
        inviter_times = [t for t in inviter_times if now - t < INVITE_RATE_WINDOW]
        if len(inviter_times) >= INVITE_RATE_MAX:
            await interaction.response.send_message(
                "You're sending too many invites! Please wait before sending more.", ephemeral=True)
            return
        inviter_times.append(now)
        self.cog._invite_send_rate[self.user_id] = inviter_times
        # --- END AI-MODIFIED ---

        await _db_exec(self.cog.bot,
            """INSERT INTO lg_family_invites (family_id, from_userid, to_userid, status, created_at)
               VALUES (%s, %s, %s, 'PENDING', NOW())
               ON CONFLICT (family_id, to_userid)
               DO UPDATE SET status = 'PENDING', from_userid = %s, created_at = NOW()""",
            self.family_id, self.user_id, target_id, self.user_id)

        await interaction.response.send_message(
            str(_p(
                'success:invite|sent',
                '\u2709\uFE0F Invite sent to **{name}**!',
            )).format(name=target_name),
            ephemeral=True)

        # --- AI-MODIFIED (2026-03-24) ---
        # Purpose: DM the invitee with accept/decline buttons, respecting notification prefs and rate limits
        try:
            target_pref_rows = await _db_fetch(self.cog.bot,
                "SELECT drop_notif FROM lg_pets WHERE userid = %s", target_id)
            pref = 'ALL'
            if target_pref_rows:
                pref = target_pref_rows[0].get('drop_notif') or 'ALL'
                if hasattr(pref, 'value'):
                    pref = pref.value
            if pref == 'MUTED':
                return

            now = _time.time()
            DM_RATE_MAX = 5
            DM_RATE_WINDOW = 86400
            target_times = self.cog._invite_dm_rate.get(target_id, [])
            target_times = [t for t in target_times if now - t < DM_RATE_WINDOW]
            if len(target_times) >= DM_RATE_MAX:
                return
            target_times.append(now)
            self.cog._invite_dm_rate[target_id] = target_times

            inv_rows = await _db_fetch(self.cog.bot,
                "SELECT invite_id FROM lg_family_invites WHERE family_id = %s AND to_userid = %s AND status = 'PENDING'",
                self.family_id, target_id)
            invite_id = inv_rows[0]['invite_id'] if inv_rows else None
            if not invite_id:
                return

            fam = await _db_fetch(self.cog.bot,
                "SELECT name, level FROM lg_families WHERE family_id = %s", self.family_id)
            family_name = fam[0]['name'] if fam else 'Unknown'
            family_level = fam[0].get('level') or 1 if fam else 1

            inviter_rows = await _db_fetch(self.cog.bot,
                "SELECT name FROM user_config WHERE userid = %s", self.user_id)
            inviter_name = inviter_rows[0]['name'] if inviter_rows else str(self.user_id)

            mem_count = await _db_fetch(self.cog.bot,
                "SELECT COUNT(*) as cnt FROM lg_family_members WHERE family_id = %s AND left_at IS NULL",
                self.family_id)
            member_count = mem_count[0]['cnt'] if mem_count else 0

            member_line = str(_p(
                'embed:family_invite|desc:members',
                '{count} member(s)',
            )).format(count=member_count)

            embed = discord.Embed(
                title=str(_p('embed:family_invite|title', '\U0001F4E8 Family Invite!')),
                description=str(_p(
                    'embed:family_invite|desc',
                    '**{inviter}** has invited you to join their family!\n\n'
                    '\U0001F3E0 **{family_name}**\n'
                    '\u2B50 Level {family_level} \u2022 {member_line}\n\n'
                    'Use the buttons below to respond, or visit `/pet` \u2192 Family.',
                )).format(
                    inviter=inviter_name,
                    family_name=family_name,
                    family_level=family_level,
                    member_line=member_line,
                ),
                color=0x5865F2,
            )
            embed.set_footer(text=str(_p(
                'embed:family_invite|footer',
                'Manage families at {url}',
            )).format(url=f'{WEBSITE_URL}/pet/family'))

            user = self.cog.bot.get_user(target_id)
            if user is None:
                user = await self.cog.bot.fetch_user(target_id)
            if user:
                view = FamilyInviteNotificationView(invite_id)
                await user.send(embed=embed, view=view)
        except discord.Forbidden:
            pass
        except Exception:
            logger.debug(f"Failed to DM family invite to {target_id}")
        # --- END AI-MODIFIED ---


# --- AI-MODIFIED (2026-03-24) ---
# Purpose: Persistent view for family invite DM notifications with accept/decline/mute buttons
class FamilyInviteNotificationView(discord.ui.View):
    """Buttons attached to family invite DM notifications.
    Uses dynamic custom_ids (invite_id encoded) handled by on_interaction listener."""

    def __init__(self, invite_id: int):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            label=_p('ui:family_invite_notif|button:accept|label', 'Accept'), emoji="\u2705",
            style=discord.ButtonStyle.green,
            custom_id=f"lg:faminv:accept:{invite_id}"
        ))
        self.add_item(discord.ui.Button(
            label=_p('ui:family_invite_notif|button:decline|label', 'Decline'), emoji="\u274C",
            style=discord.ButtonStyle.red,
            custom_id=f"lg:faminv:decline:{invite_id}"
        ))
        self.add_item(discord.ui.Button(
            label=_p('ui:family_invite_notif|button:notif_settings|label', 'Notification Settings'), emoji="\U0001F514",
            style=discord.ButtonStyle.grey,
            custom_id="lg:faminv:notif_toggle"
        ))
        self.add_item(discord.ui.Button(
            label=_p('ui:family_invite_notif|button:view_family|label', 'View Family'),
            url=f"{WEBSITE_URL}/pet/family",
            style=discord.ButtonStyle.link
        ))
# --- END AI-MODIFIED ---


# --- END AI-GENERATED ---


# ============================================================
# Main Pet View
# ============================================================
# --- AI-REPLACED (2026-03-16) ---
# Reason: Use custom LionGotchi emojis for buttons instead of generic Unicode
# What the new code does better: Buttons show pixel-art gameboy icons when configured
# --- Original code (commented out for rollback) ---
# class PetView(discord.ui.View):
#     def __init__(self, cog: 'LionGotchiCog', user_id: int, guild_id: int, fullscreen: bool = False):
#         super().__init__(timeout=180)
#         self.cog = cog
#         self.user_id = user_id
#         self.guild_id = guild_id
#         self.fullscreen = fullscreen
#
#         toggle_label = "\U0001F3AE Gameboy" if fullscreen else "\U0001F4FA Full Screen"
#         toggle_btn = discord.ui.Button(
#             label=toggle_label,
#             style=discord.ButtonStyle.blurple if fullscreen else discord.ButtonStyle.grey,
#             row=2
#         )
#         toggle_btn.callback = self._toggle_view
#         self.add_item(toggle_btn)
# --- End original code ---
class PetView(discord.ui.View):
    def __init__(self, cog: 'LionGotchiCog', user_id: int, guild_id: int, fullscreen: bool = False):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.fullscreen = fullscreen

        # --- AI-MODIFIED (2026-03-16) ---
        # Purpose: Simplified button layout - removed inventory_button emoji (button removed),
        #          moved toggle to row 1, added website link button
        # self.inventory_button.emoji = _lg_partial('lg_giftbox', "\U0001F392")
        self.feed_button.emoji = _lg_partial('lg_steak', "\U0001F356")
        self.bathe_button.emoji = _lg_partial('lg_soap', "\U0001F9FC")
        self.sleep_button.emoji = _lg_partial('lg_sleep', "\U0001F4A4")
        self.farm_button.emoji = _lg_partial('lg_trophy', "\U0001F33F")

        toggle_label = (
            str(_p('ui:pet|button:toggle|gameboy', "\U0001F3AE Gameboy"))
            if fullscreen else
            str(_p('ui:pet|button:toggle|fullscreen', "\U0001F4FA Full Screen"))
        )
        toggle_btn = discord.ui.Button(
            label=toggle_label,
            style=discord.ButtonStyle.blurple if fullscreen else discord.ButtonStyle.grey,
            row=1
        )
        toggle_btn.callback = self._toggle_view
        self.add_item(toggle_btn)

        self.add_item(discord.ui.Button(
            label=_p('ui:pet|button:manage|label', "Manage Pet"),
            url=f"{WEBSITE_URL}/pet",
            style=discord.ButtonStyle.link,
            row=1
        ))

        # --- AI-MODIFIED (2026-03-24) ---
        # Purpose: Friends button to open the friends hub view
        friends_btn = discord.ui.Button(
            label=_p('ui:pet|button:friends|label', "Friends"),
            emoji="\U0001F465",
            style=discord.ButtonStyle.blurple,
            row=1
        )
        friends_btn.callback = self._open_friends
        self.add_item(friends_btn)
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-03-24) ---
        # Purpose: Family button to open the family hub view
        family_btn = discord.ui.Button(
            label=_p('ui:pet|button:family|label', "Family"),
            emoji="\U0001F3E0",
            style=discord.ButtonStyle.blurple,
            row=1
        )
        family_btn.callback = self._open_family
        self.add_item(family_btn)
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-03-24) ---
        # Purpose: Beta bug report link button to support server
        self.add_item(discord.ui.Button(
            label=_p('ui:pet|button:report_bug|label', "Report a Bug"),
            emoji="\U0001F41B",
            url="https://discord.gg/the-study-lions-780195610154237993",
            style=discord.ButtonStyle.link,
            row=2
        ))
        # --- END AI-MODIFIED ---
        # --- END AI-MODIFIED ---
# --- END AI-REPLACED ---

    async def _toggle_view(self, interaction: discord.Interaction):
        new_mode = not self.fullscreen
        await _db_exec(self.cog.bot,
            "UPDATE lg_pets SET fullscreen_mode = %s WHERE userid = %s",
            new_mode, self.user_id)
        await self.cog._show_pet(interaction, edit=True)

    # --- AI-MODIFIED (2026-03-24) ---
    # Purpose: Open the friends hub from the pet view
    async def _open_friends(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = FriendsHubView(self.cog, self.user_id, self.guild_id)
        await view.load_data()
        await interaction.edit_original_response(
            content=None, embed=view.make_embed(), view=view, attachments=[])
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-24) ---
    # Purpose: Open the family hub from the pet view
    async def _open_family(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = FamilyHubView(self.cog, self.user_id, self.guild_id)
        await view.load_data()
        content, file, embed = view.make_content_and_file()
        kwargs = {'view': view}
        if file:
            kwargs['content'] = content
            kwargs['embed'] = None
            kwargs['attachments'] = [file]
        else:
            kwargs['content'] = None
            kwargs['embed'] = embed
            kwargs['attachments'] = []
        await interaction.edit_original_response(**kwargs)
    # --- END AI-MODIFIED ---

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                str(_p('error:pet|not_yours', "This isn't your pet! Use `/pet` to see yours.")),
                ephemeral=True
            )
            return False
        return True

    # --- AI-REPLACED (2026-03-16) ---
    # Reason: Simplified button layout - emoji-only care buttons, removed management buttons
    # What the new code does better: Cleaner UI; Inventory/Shop/Skin/Settings/Craft moved to website
    # --- Original code (commented out for rollback) ---
    # @discord.ui.button(label="Feed", ..., row=0) -> feed_button: _feed_pet
    # @discord.ui.button(label="Bathe", ..., row=0) -> bathe_button: _bathe_pet
    # @discord.ui.button(label="Sleep", ..., row=0) -> sleep_button: _sleep_pet
    # @discord.ui.button(label="Inventory", ..., row=1) -> inventory_button: InventoryView
    # @discord.ui.button(label="Shop", ..., row=1) -> shop_button: ShopView
    # @discord.ui.button(label="Room", ..., row=1) -> room_button: RoomView
    # @discord.ui.button(label="Skin", ..., row=1) -> skin_button: SkinView
    # @discord.ui.button(label="Settings", ..., row=1) -> settings_button: PetNameModal
    # @discord.ui.button(label="Craft", ..., row=2) -> craft_button: CraftView
    # @discord.ui.button(label="Farm", ..., row=2) -> farm_button: FarmView
    # --- End original code ---

    @discord.ui.button(emoji="\U0001F356", style=discord.ButtonStyle.green, row=0)
    async def feed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._feed_pet(interaction)

    @discord.ui.button(emoji="\U0001F9FC", style=discord.ButtonStyle.blurple, row=0)
    async def bathe_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._bathe_pet(interaction)

    @discord.ui.button(emoji="\U0001F4A4", style=discord.ButtonStyle.grey, row=0)
    async def sleep_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._sleep_pet(interaction)

    # --- AI-REPLACED (2026-03-24) ---
    # Reason: Old inventory button showed a plain-text list capped at 15 items with one link button
    # What the new code does better: Rich paginated embed with rarity colors, enhancement levels,
    #   equipped badges, and link buttons to Equip/Buy&Sell/Enhance pages on the website
    # --- Original code (commented out for rollback) ---
    # @discord.ui.button(emoji="\U0001F392", style=discord.ButtonStyle.grey, row=0)
    # async def inventory_button(self, interaction, button):
    #     inv_rows = await _db_fetch(self.cog.bot, "SELECT i.name, i.rarity::text ... LIMIT 15", self.user_id)
    #     text = bullet list of items or "empty"
    #     inv_view = discord.ui.View() + "Manage on Website" link button
    #     await interaction.response.send_message(content=text, ephemeral=True, view=inv_view)
    # --- End original code ---
    @discord.ui.button(emoji="\U0001F392", style=discord.ButtonStyle.grey, row=0)
    async def inventory_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            rows = await _db_fetch(self.cog.bot,
                """SELECT i.name, i.rarity::text AS rarity, i.category::text AS category,
                          i.slot::text AS slot, ui.enhancement_level, ui.quantity AS qty,
                          (pe.itemid IS NOT NULL) AS equipped
                   FROM lg_user_inventory ui
                   JOIN lg_items i ON ui.itemid = i.itemid
                   LEFT JOIN lg_pet_equipment pe
                        ON pe.userid = ui.userid AND pe.itemid = ui.itemid
                   WHERE ui.userid = %s AND ui.quantity > 0
                   ORDER BY i.rarity DESC, i.category, i.name""",
                self.user_id
            ) or []

            for r in rows:
                r['rarity'] = _clean_rarity(r.get('rarity', 'COMMON'))

            view = InventoryPaginatorView(self.cog, self.user_id, self.guild_id, rows)
            await self.cog._add_vote_btn(view, self.user_id, self.guild_id)
            await interaction.response.send_message(
                embed=view.make_embed(), view=view, ephemeral=True
            )
        except Exception as e:
            logger.error(f"Inventory button failed: {e}\n{traceback.format_exc()}")
            try:
                await interaction.response.send_message(
                    str(_p('error:backpack|load_failed', "Could not load your backpack. Please try again.")),
                    ephemeral=True
                )
            except Exception:
                pass
    # --- END AI-REPLACED ---

    @discord.ui.button(label=_p('ui:pet|button:farm|label', "Farm"), emoji="\U0001F33F", style=discord.ButtonStyle.green, row=0)
    # --- END AI-MODIFIED ---
    async def farm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        farm_view = FarmView(self.cog, self.user_id, interaction.guild, fullscreen=self.fullscreen)
        await farm_view.load_farm()
        # --- AI-MODIFIED (2026-03-19) ---
        await self.cog._add_vote_btn(farm_view, self.user_id, interaction.guild_id)
        # --- END AI-MODIFIED ---
        await farm_view.show_farm(interaction)
    # --- END AI-REPLACED ---


# ============================================================
# Main Cog
# ============================================================
class LionGotchiCog(LionCog):
    # --- AI-MODIFIED (2026-03-15) ---
    # Purpose: Added message accumulator for responsive farm growth (bypasses text tracker batching)
    FARM_MSG_FLUSH_SECONDS = 30

    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = bot.db.load_registry(LionGotchiData())
        self._feed_cooldowns: dict[int, datetime] = {}
        self._bathe_cooldowns: dict[int, datetime] = {}
        # --- AI-MODIFIED (2026-03-19) ---
        # Purpose: Sleep cooldown + pet warning notification cooldown
        self._sleep_cooldowns: dict[int, datetime] = {}
        self._pet_warning_cooldowns: dict[int, datetime] = {}
        # --- END AI-MODIFIED ---
        self._last_pet_name: str = "Leo"
        self._farm_msg_counts: dict[int, int] = {}
        self._farm_flush_task: asyncio.Task | None = None
        # --- AI-MODIFIED (2026-03-16) ---
        # Purpose: Cooldown tracking for drop notification rate limiting
        self._drop_notif_cooldowns: dict[int, datetime] = {}
        # --- AI-MODIFIED (2026-03-16) ---
        # Purpose: Per-message drop counter -- checks drops every N messages instead of waiting for session batch
        self._drop_msg_counts: dict[int, int] = {}
        self._first_encounter_sent: set[int] = set()
        # --- AI-MODIFIED (2026-03-20) ---
        # Purpose: Onboarding GIF renderer for visual tutorial and first encounter
        self._onboarding_gifs = OnboardingGIFs()
        # --- END AI-MODIFIED ---
        # --- AI-MODIFIED (2026-03-17) ---
        # Purpose: Anti-cheat daily caps and text message cooldown tracking
        self._daily_gold_earned: dict[int, float] = {}
        self._daily_xp_earned: dict[int, float] = {}
        self._daily_drops: dict[int, int] = {}
        self._daily_voice_minutes: dict[int, float] = {}  # VC Study Streak tracking
        self._daily_reset_date: str = ''
        self._last_lg_msg_time: dict[int, float] = {}
        # --- END AI-MODIFIED ---
        # --- END AI-MODIFIED ---
        # --- AI-MODIFIED (2026-03-20) ---
        # Purpose: TTL cache for guild LionGotchi config (avoids per-event DB queries)
        self._guild_lg_cache: dict[int, tuple[float, dict]] = {}
        self._guild_lg_cache_ttl = 300
        # --- AI-MODIFIED (2026-03-24) ---
        # Purpose: Rate limit tracking for family invite sends and DM notifications
        self._invite_send_rate: dict[int, list[float]] = {}
        self._invite_dm_rate: dict[int, list[float]] = {}
        # --- END AI-MODIFIED ---
        # --- END AI-MODIFIED ---
        # --- AI-MODIFIED (2026-04-10) ---
        # Purpose: One-time adoption nudge tracking -- skip set, rate-limit deque, stats caches
        self._nudge_skip_users: set[int] = set()
        self._nudge_send_times: list[float] = []
        self._last_nudge_sent: float = 0.0
        self._cached_item_drop_count: int = 0
        self._cached_farm_count: int = 0
        # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-19) ---
    # Purpose: Vote button helper for raw discord.ui.View pet UIs
    async def _add_vote_btn(self, view, user_id, guild_id=None):
        voting = self.bot.get_cog('TopggCog')
        if voting:
            await voting.add_vote_to_view(view, user_id, guild_id)
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-17) ---
    # Purpose: Anti-cheat daily cap helpers -- reset on date change, track per-user daily totals

    def _check_daily_reset(self):
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        if today != self._daily_reset_date:
            self._daily_gold_earned.clear()
            self._daily_xp_earned.clear()
            self._daily_drops.clear()
            self._daily_voice_minutes.clear()
            self._daily_reset_date = today

    def _cap_gold(self, userid: int, amount: int) -> int:
        self._check_daily_reset()
        earned = self._daily_gold_earned.get(userid, 0)
        remaining = max(0, DAILY_GOLD_CAP - earned)
        capped = min(amount, remaining)
        if capped > 0:
            self._daily_gold_earned[userid] = earned + capped
        return capped

    def _cap_xp(self, userid: int, amount: int) -> int:
        self._check_daily_reset()
        earned = self._daily_xp_earned.get(userid, 0)
        remaining = max(0, DAILY_XP_CAP - earned)
        capped = min(amount, remaining)
        if capped > 0:
            self._daily_xp_earned[userid] = earned + capped
        return capped

    def _can_drop(self, userid: int) -> bool:
        self._check_daily_reset()
        return self._daily_drops.get(userid, 0) < DAILY_DROP_CAP

    def _record_drop(self, userid: int):
        self._check_daily_reset()
        self._daily_drops[userid] = self._daily_drops.get(userid, 0) + 1

    # --- AI-MODIFIED (2026-03-22) ---
    # Purpose: VC Study Streak -- track daily voice minutes and compute rarity boost
    def _record_voice_minutes(self, userid: int, minutes: float):
        self._check_daily_reset()
        self._daily_voice_minutes[userid] = self._daily_voice_minutes.get(userid, 0) + minutes

    def _get_vc_rarity_boost(self, userid: int) -> tuple[float, str, int]:
        """Returns (boost_multiplier, tier_name, daily_minutes)."""
        self._check_daily_reset()
        minutes = self._daily_voice_minutes.get(userid, 0)
        from .gameplay import calc_vc_rarity_boost
        boost, name = calc_vc_rarity_boost(minutes)
        return boost, name, int(minutes)
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-20) ---
    # Purpose: Show daily gold/XP progress in drop and level-up notifications
    def _format_daily_progress(self, userid: int) -> str:
        """Format daily gold/XP cap progress for display in notifications."""
        self._check_daily_reset()
        gold_earned = int(self._daily_gold_earned.get(userid, 0))
        xp_earned = int(self._daily_xp_earned.get(userid, 0))
        gold_pct = min(100, int(gold_earned / DAILY_GOLD_CAP * 100)) if DAILY_GOLD_CAP else 0
        xp_pct = min(100, int(xp_earned / DAILY_XP_CAP * 100)) if DAILY_XP_CAP else 0
        gold_warn = " \u26A0\uFE0F" if gold_pct >= 90 else ""
        xp_warn = " \u26A0\uFE0F" if xp_pct >= 90 else ""
        return (
            f"\U0001F4CA Daily: **{gold_earned:,}**/{DAILY_GOLD_CAP:,}G{gold_warn}"
            f" | **{xp_earned:,}**/{DAILY_XP_CAP:,} XP{xp_warn}"
        )
    # --- END AI-MODIFIED ---

    def _msg_on_cooldown(self, userid: int) -> bool:
        now = _time.monotonic()
        last = self._last_lg_msg_time.get(userid, 0)
        if now - last < LG_MSG_COOLDOWN_SECONDS:
            return True
        self._last_lg_msg_time[userid] = now
        return False
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: Helper to fetch user subscription tier and server premium status for gameplay functions
    async def _get_premium_context(self, userid, guildid):
        premium_cog = self.bot.get_cog('PremiumCog')
        user_tier = 'NONE'
        server_premium = False
        if premium_cog:
            if hasattr(premium_cog, 'get_user_subscription_tier'):
                try:
                    user_tier = await premium_cog.get_user_subscription_tier(userid)
                except Exception:
                    pass
            if hasattr(premium_cog, 'is_premium_guild') and guildid:
                try:
                    server_premium = await premium_cog.is_premium_guild(guildid)
                except Exception:
                    pass
        return user_tier, server_premium
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-20) ---
    # Purpose: Fetch all guild LG settings in one query with TTL cache
    async def _get_guild_lg_config(self, guildid: int) -> dict:
        """Return guild LionGotchi config dict with TTL caching."""
        now = _time.monotonic()
        cached = self._guild_lg_cache.get(guildid)
        if cached and (now - cached[0]) < self._guild_lg_cache_ttl:
            return cached[1]

        defaults = {
            'lg_enabled': True,
            'lg_drop_channel': None,
            'lg_guild_display_name': None,
            'lg_teaser_enabled': True,
            'lg_activity_role': None,
            'lg_drop_delete_after': None,
        }
        try:
            rows = await _db_fetch(self.bot,
                "SELECT lg_enabled, lg_drop_channel, lg_guild_display_name, "
                "lg_teaser_enabled, lg_activity_role, lg_drop_delete_after "
                "FROM guild_config WHERE guildid = %s",
                guildid
            )
            if rows:
                for key in defaults:
                    val = rows[0].get(key)
                    if val is not None:
                        defaults[key] = val
        except Exception:
            logger.debug("Failed to fetch guild LG config for %s", guildid)

        self._guild_lg_cache[guildid] = (now, defaults)
        return defaults
    # --- END AI-MODIFIED ---

    async def cog_load(self):
        await self.data.init()
        self._farm_flush_task = asyncio.create_task(self._farm_flush_loop())
    # --- AI-MODIFIED (2026-03-22) ---
    # Purpose: Register persistent notification views so buttons survive bot restarts,
    #          plus existing startup tasks (pet count, GIFs, encounter set, status rotation)
        self.bot.add_view(DropNotificationView())
        self.bot.add_view(LevelUpNotificationView())
        self.bot.add_view(FirstDropView())
        asyncio.create_task(self._refresh_pet_count())
        asyncio.create_task(self._onboarding_gifs.preload_all())
        asyncio.create_task(self._populate_encounter_set())
        self._launch_status_task = asyncio.create_task(self._launch_status_rotation())
        # --- AI-MODIFIED (2026-04-10) ---
        # Purpose: Register adoption nudge persistent view + startup tasks
        self.bot.add_view(AdoptionNudgeView())
        asyncio.create_task(self._refresh_nudge_stats())
        asyncio.create_task(self._populate_nudge_skip_set())
        # --- END AI-MODIFIED ---
        # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-24) ---
    # Purpose: Persistent handler for family invite DM buttons (accept/decline/mute).
    #          Uses on_interaction listener because accept/decline custom_ids contain
    #          dynamic invite_ids and can't be registered as static persistent views.
    @cmds.Cog.listener('on_interaction')
    async def on_family_invite_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        cid = interaction.data.get('custom_id', '')
        if not cid.startswith('lg:faminv:'):
            return

        if cid == 'lg:faminv:notif_toggle':
            await _handle_notif_toggle(interaction)
            return

        try:
            parts = cid.split(':')
            action = parts[2]
            invite_id = int(parts[3])
        except (IndexError, ValueError):
            return

        uid = interaction.user.id
        if action == 'accept':
            await self._handle_dm_invite_accept(interaction, invite_id, uid)
        elif action == 'decline':
            await self._handle_dm_invite_decline(interaction, invite_id, uid)

    async def _handle_dm_invite_accept(self, interaction: discord.Interaction, invite_id: int, uid: int):
        try:
            inv = await _db_fetch(self.bot,
                """SELECT fi.family_id, fi.to_userid, f.name AS family_name, f.xp, f.max_members
                   FROM lg_family_invites fi
                   JOIN lg_families f ON f.family_id = fi.family_id
                   WHERE fi.invite_id = %s AND fi.status = 'PENDING'""",
                invite_id)
            if not inv or inv[0]['to_userid'] != uid:
                await interaction.response.edit_message(
                    embed=discord.Embed(
                        title=str(_p('embed:invite_expired|title', '\u23F3 Invite Expired')),
                        description=str(_p(
                            'embed:invite_expired|desc',
                            'This invite is no longer valid. It may have been accepted, declined, or withdrawn.',
                        )),
                        color=0x95a5a6,
                    ).set_footer(text=str(_p(
                        'embed:invite_expired|footer',
                        'Check /pet \u2192 Family for new invites',
                    ))),
                    view=None)
                return

            already = await _db_fetch(self.bot,
                "SELECT family_id FROM lg_family_members WHERE userid = %s AND left_at IS NULL", uid)
            if already:
                await interaction.response.send_message(
                    str(_p(
                        'error:family|already_in_family_dm',
                        "You're already in a family! Leave your current family first.",
                    )),
                    ephemeral=True)
                return

            COOLDOWN_DAYS = 7
            last_left = await _db_fetch(self.bot,
                """SELECT left_at FROM lg_family_members
                   WHERE userid = %s AND left_at IS NOT NULL
                   ORDER BY left_at DESC LIMIT 1""", uid)
            if last_left and last_left[0].get('left_at'):
                left_at = last_left[0]['left_at']
                if left_at.tzinfo is None:
                    left_at = left_at.replace(tzinfo=timezone.utc)
                days_since = (datetime.now(timezone.utc) - left_at).total_seconds() / 86400
                if days_since < COOLDOWN_DAYS:
                    remaining = int(COOLDOWN_DAYS - days_since) + 1
                    await interaction.response.send_message(
                        str(_p(
                            'error:family|cooldown',
                            'You recently left a family. Cooldown: **{days} day(s)** remaining.',
                        )).format(days=remaining),
                        ephemeral=True)
                    return

            family_id = inv[0]['family_id']
            family_name = inv[0]['family_name'] or 'Unknown Family'

            fam_xp = int(inv[0].get('xp') or 0)
            fam_level = family_level_from_xp(fam_xp)
            max_mem = max(inv[0].get('max_members') or 10, 10 + (fam_level - 1) // 2)
            mem_count = await _db_fetch(self.bot,
                "SELECT COUNT(*) as cnt FROM lg_family_members WHERE family_id = %s AND left_at IS NULL",
                family_id)
            if (mem_count[0]['cnt'] or 0) >= max_mem:
                await interaction.response.send_message(
                    str(_p(
                        'error:family|full',
                        'This family is full! They need to level up to unlock more slots.',
                    )),
                    ephemeral=True)
                return

            await _db_exec(self.bot,
                "UPDATE lg_family_invites SET status = 'ACCEPTED' WHERE invite_id = %s", invite_id)
            await _db_exec(self.bot,
                """INSERT INTO lg_family_members (family_id, userid, role, joined_at, contribution_xp)
                   VALUES (%s, %s, 'MEMBER', NOW(), 0)
                   ON CONFLICT (family_id, userid) DO UPDATE SET left_at = NULL, role = 'MEMBER',
                   joined_at = NOW(), contribution_xp = 0""",
                family_id, uid)

            await interaction.response.edit_message(
                embed=discord.Embed(
                    title=str(_p('embed:joined_family|title', '\u2705 Joined Family!')),
                    description=str(_p(
                        'embed:joined_family|desc',
                        'You are now a member of **{name}**!\n\n'
                        'Use `/pet` \u2192 Family to see your new family.',
                    )).format(name=family_name),
                    color=0x57F287,
                ).set_footer(text=str(_p(
                    'embed:joined_family|footer',
                    'Manage your family at {url}',
                )).format(url=f'{WEBSITE_URL}/pet/family')),
                view=None)
        except Exception:
            logger.debug(f"Failed to handle DM invite accept for user {uid}, invite {invite_id}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    str(_p(
                        'error:invite|generic_retry',
                        'Something went wrong. Try `/pet` \u2192 Family instead.',
                    )),
                    ephemeral=True)

    async def _handle_dm_invite_decline(self, interaction: discord.Interaction, invite_id: int, uid: int):
        try:
            inv = await _db_fetch(self.bot,
                """SELECT fi.to_userid, f.name AS family_name
                   FROM lg_family_invites fi
                   JOIN lg_families f ON f.family_id = fi.family_id
                   WHERE fi.invite_id = %s AND fi.status = 'PENDING'""",
                invite_id)
            if not inv or inv[0]['to_userid'] != uid:
                await interaction.response.edit_message(
                    embed=discord.Embed(
                        title=str(_p('embed:invite_expired|title', '\u23F3 Invite Expired')),
                        description=str(_p(
                            'embed:invite_expired|desc',
                            'This invite is no longer valid. It may have been accepted, declined, or withdrawn.',
                        )),
                        color=0x95a5a6,
                    ).set_footer(text=str(_p(
                        'embed:invite_expired|footer',
                        'Check /pet \u2192 Family for new invites',
                    ))),
                    view=None)
                return

            family_name = inv[0]['family_name'] or 'Unknown Family'

            await _db_exec(self.bot,
                "UPDATE lg_family_invites SET status = 'DECLINED' WHERE invite_id = %s", invite_id)

            await interaction.response.edit_message(
                embed=discord.Embed(
                    title=str(_p('embed:invite_declined|title', '\u274C Invite Declined')),
                    description=str(_p(
                        'embed:invite_declined|desc',
                        'You declined the invite from **{name}**.',
                    )).format(name=family_name),
                    color=0xED4245,
                ).set_footer(text=str(_p(
                    'embed:invite_declined|footer',
                    'You can always join a family later via /pet \u2192 Family',
                ))),
                view=None)
        except Exception:
            logger.debug(f"Failed to handle DM invite decline for user {uid}, invite {invite_id}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    str(_p(
                        'error:invite|generic_retry',
                        'Something went wrong. Try `/pet` \u2192 Family instead.',
                    )),
                    ephemeral=True)
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-20) ---
    # Purpose: Periodically refresh pet count for social proof in first encounter messages
    async def _refresh_pet_count(self):
        while True:
            try:
                rows = await _db_fetch(self.bot,
                    "SELECT COUNT(*) AS cnt FROM lg_pets"
                )
                if rows:
                    self._cached_pet_count = rows[0].get('cnt', 0)
            except Exception:
                logger.debug("Failed to refresh pet count for social proof")
            await asyncio.sleep(3600)

    # --- AI-MODIFIED (2026-04-10) ---
    # Purpose: Hourly stats cache for adoption nudge social proof (items dropped + active farms)
    async def _refresh_nudge_stats(self):
        await self.bot.wait_until_ready()
        while True:
            try:
                rows = await _db_fetch(self.bot,
                    "SELECT COALESCE(SUM(quantity), 0) AS cnt FROM lg_user_inventory WHERE source = 'DROP'"
                )
                if rows:
                    self._cached_item_drop_count = rows[0].get('cnt', 0)
            except Exception:
                logger.debug("Failed to refresh item drop count for nudge")
            try:
                rows = await _db_fetch(self.bot,
                    "SELECT COUNT(DISTINCT userid) AS cnt FROM lg_user_farm WHERE seed_id IS NOT NULL"
                )
                if rows:
                    self._cached_farm_count = rows[0].get('cnt', 0)
            except Exception:
                logger.debug("Failed to refresh farm count for nudge")
            await asyncio.sleep(3600)

    async def _populate_nudge_skip_set(self):
        """Pre-populate skip set with pet owners and already-nudged users on startup."""
        await self.bot.wait_until_ready()
        try:
            rows = await _db_fetch(self.bot, "SELECT userid FROM lg_pets")
            for row in rows:
                self._nudge_skip_users.add(row['userid'])
            rows2 = await _db_fetch(self.bot,
                "SELECT userid FROM user_config WHERE lg_nudge_sent_at IS NOT NULL"
            )
            for row in rows2:
                self._nudge_skip_users.add(row['userid'])
            logger.info(f"Populated nudge skip set with {len(self._nudge_skip_users)} users")
        except Exception:
            logger.debug("Failed to populate nudge skip set from DB")
    # --- END AI-MODIFIED ---

    async def _populate_encounter_set(self):
        """Pre-populate _first_encounter_sent with existing pet owners on startup.

        Users who already have pets should never receive the first encounter
        message. Users without pets who saw it before a restart will see it
        again -- this is desirable for launch conversion.
        """
        try:
            rows = await _db_fetch(self.bot, "SELECT userid FROM lg_pets")
            for row in rows:
                self._first_encounter_sent.add(row['userid'])
            logger.info(f"Populated first_encounter_sent with {len(rows)} pet owners")
        except Exception:
            logger.debug("Failed to populate first_encounter_sent from DB")

    LAUNCH_STATUS_ENABLED = True
    LAUNCH_STATUS_INTERVAL = 300
    LAUNCH_STATUS_DURATION = 30

    async def _launch_status_rotation(self):
        """Periodically show a LionGotchi promo status during launch week.

        Every LAUNCH_STATUS_INTERVAL seconds, sets the bot's status to a
        LionGotchi promo message for LAUNCH_STATUS_DURATION seconds.
        The normal presence system then restores the regular status.
        Set LAUNCH_STATUS_ENABLED = False to disable after launch.
        """
        await self.bot.wait_until_ready()
        await asyncio.sleep(60)

        promo_messages = [
            "NEW: /pet \u2014 Adopt your LionGotchi!",
            "/pet \u2014 Earn gear while you're productive!",
            "/pet \u2014 Farm, trade, collect!",
        ]
        idx = 0

        while self.LAUNCH_STATUS_ENABLED:
            try:
                msg = promo_messages[idx % len(promo_messages)]
                idx += 1
                await self.bot.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.playing,
                        name=msg
                    ),
                    status=discord.Status.online
                )
                await asyncio.sleep(self.LAUNCH_STATUS_DURATION)
            except Exception:
                logger.debug("Launch status rotation error")
            await asyncio.sleep(self.LAUNCH_STATUS_INTERVAL)
    # --- END AI-MODIFIED ---

    async def cog_unload(self):
        if self._farm_flush_task and not self._farm_flush_task.done():
            self._farm_flush_task.cancel()
        await self._flush_farm_messages()

    async def _farm_flush_loop(self):
        """Periodically flush accumulated message counts to farm growth."""
        try:
            while True:
                await asyncio.sleep(self.FARM_MSG_FLUSH_SECONDS)
                await self._flush_farm_messages()
        except asyncio.CancelledError:
            pass

    async def _flush_farm_messages(self):
        """Flush all accumulated message counts, applying farm growth for each user."""
        if not self._farm_msg_counts:
            return
        pending = self._farm_msg_counts.copy()
        self._farm_msg_counts.clear()
        for userid, count in pending.items():
            if count < 1:
                continue
            try:
                # --- AI-MODIFIED (2026-03-16) ---
                # Purpose: Pass user subscription tier to farm growth (no guildid available in flush loop)
                user_tier, _ = await self._get_premium_context(userid, None)
                # await process_farm_growth(self.bot, userid, message_count=count)
                await process_farm_growth(self.bot, userid, message_count=count, user_tier=user_tier)
                # --- END AI-MODIFIED ---
                # --- AI-MODIFIED (2026-03-30) ---
                # Purpose: Also grow family farm plots from message activity
                await process_family_farm_growth(self.bot, userid, message_count=count, user_tier=user_tier)
                # --- END AI-MODIFIED ---
            except Exception:
                logger.exception(f"Farm growth flush failed for {userid}")
    # --- END AI-MODIFIED ---

    # ---- Pet creation & decay ----

    async def _get_or_create_pet(self, userid: int):
        pet = self.data.Pet._cache_.get(userid)
        if pet is None:
            pet = await self.data.Pet.fetch(userid)
        if pet is None:
            await _db_exec(self.bot,
                "INSERT INTO user_config (userid) VALUES (%s) ON CONFLICT DO NOTHING",
                userid
            )
            await _db_exec(self.bot,
                "INSERT INTO lg_pets (userid) VALUES (%s) ON CONFLICT DO NOTHING", userid
            )
            await _db_exec(self.bot,
                "INSERT INTO lg_user_rooms (userid, room_id) VALUES (%s, 1) ON CONFLICT DO NOTHING", userid
            )
            await _db_exec(self.bot, "UPDATE lg_pets SET active_room_id=1 WHERE userid=%s", userid)
            # --- AI-REPLACED (2026-03-17) ---
            # Reason: Hardcoded skin_id=1 no longer valid after DB reseed.
            # What the new code does better: Looks up the first FREE skin dynamically.
            # --- Original code (commented out for rollback) ---
            # await _db_exec(self.bot, "UPDATE lg_pets SET active_gameboy_skin_id=1 WHERE userid=%s", userid)
            # --- End original code ---
            first_skin = await _db_fetch(self.bot,
                "SELECT skin_id FROM lg_gameboy_skins WHERE unlock_type = 'FREE' ORDER BY skin_id LIMIT 1"
            )
            default_skin_id = first_skin[0]['skin_id'] if first_skin else None
            if default_skin_id:
                await _db_exec(self.bot, "UPDATE lg_pets SET active_gameboy_skin_id=%s WHERE userid=%s", default_skin_id, userid)
            # --- END AI-REPLACED ---

            await _db_exec(self.bot,
                """INSERT INTO lg_user_furniture (userid, slot, asset_path)
                   VALUES (%s, 'wall', 'rooms/default/wall_checker_blue.png'),
                          (%s, 'floor', 'rooms/default/floor_brown.png'),
                          (%s, 'mat', 'rooms/default/mat_blue.png'),
                          (%s, 'bed', 'rooms/default/bed_red.png'),
                          (%s, 'chair', 'rooms/default/chair_brown.png'),
                          (%s, 'lamp', 'rooms/default/lamp_yellow.png'),
                          (%s, 'table', 'rooms/default/table_brown.png'),
                          (%s, 'window', 'rooms/default/window_blue.png')
                   ON CONFLICT DO NOTHING""",
                userid, userid, userid, userid, userid, userid, userid, userid
            )

            for plot_id in range(15):
                await _db_exec(self.bot,
                    "INSERT INTO lg_user_farm (userid, plot_id, growth_stage, dead) VALUES (%s, %s, 0, false) ON CONFLICT DO NOTHING",
                    userid, plot_id
                )

            # --- AI-MODIFIED (2026-03-16) ---
            # Purpose: Bypass cache after raw SQL insert -- cache holds a None sentinel from earlier lookup
            pet = await self.data.Pet.fetch(userid, cached=False)
            # --- END AI-MODIFIED ---
        return pet

    # --- AI-REPLACED (2026-03-19) ---
    # Reason: Stat redesign -- life is no longer updated; mood is derived from the 3 needs
    # What the new code does better: Simpler decay (just 3 needs), no confusing life penalty
    # --- Original code (commented out for rollback) ---
    # async def _apply_decay(self, pet):
    #     life_penalty = sum(1 for v in [new_food, new_bath, new_sleep] if v == 0)
    #     new_life = max(0, pet.life - life_penalty)
    #     await _db_exec(self.bot, "UPDATE lg_pets SET food=%s, bath=%s, sleep=%s, life=%s, ...")
    # --- End original code ---
    async def _apply_decay(self, pet):
        now = datetime.now(timezone.utc)
        last_decay = pet.last_decay_at
        if last_decay.tzinfo is None:
            last_decay = last_decay.replace(tzinfo=timezone.utc)
        elapsed_hours = (now - last_decay).total_seconds() / 3600
        decay_ticks = int(elapsed_hours / NEEDS_DECAY_INTERVAL_HOURS)
        # --- AI-MODIFIED (2026-05-15) ---
        # Purpose: Cap accumulated decay per wake so long absences (e.g. user gone for a month)
        # never drop stats by more than MAX_DECAY_PER_WAKE. Prevents the "I leveled up and all
        # my stats vanished" shock that's actually accumulated decay firing all at once.
        decay_ticks = min(decay_ticks, MAX_DECAY_PER_WAKE)
        # --- END AI-MODIFIED ---
        if decay_ticks > 0:
            new_food = max(0, pet.food - decay_ticks * NEEDS_DECAY_AMOUNT)
            new_bath = max(0, pet.bath - decay_ticks * NEEDS_DECAY_AMOUNT)
            new_sleep = max(0, pet.sleep - decay_ticks * NEEDS_DECAY_AMOUNT)
            await _db_exec(self.bot,
                "UPDATE lg_pets SET food=%s, bath=%s, sleep=%s, last_decay_at=%s WHERE userid=%s",
                new_food, new_bath, new_sleep, now, pet.userid
            )
            # --- AI-MODIFIED (2026-03-21) ---
            # Purpose: Sync cached pet object after raw SQL update so mood
            # calculations use actual decayed values instead of stale cache
            if pet.data is not None:
                pet.data['food'] = new_food
                pet.data['bath'] = new_bath
                pet.data['sleep'] = new_sleep
                pet.data['last_decay_at'] = now
            # --- END AI-MODIFIED ---
        return pet
    # --- END AI-REPLACED ---

    # ---- Build render state ----

    async def _build_pet_state(self, pet, guild: discord.Guild = None) -> PetState:
        # --- AI-MODIFIED (2026-03-20) ---
        # Purpose: Fetch fresh cosmetic IDs from DB -- the Pet cache doesn't see website changes
        # --- Original code (commented out for rollback) ---
        # room = await self.data.Room.fetch(pet.active_room_id) if pet.active_room_id else None
        # room_prefix = room.asset_prefix if room else "rooms/default"
        #
        # skin = await self.data.GameboySkin.fetch(pet.active_gameboy_skin_id) if pet.active_gameboy_skin_id else None
        # gameboy_skin = skin.asset_path if skin else "gameboy/frames/gameboy-basic-01.png"
        # --- End original code ---
        # --- AI-MODIFIED (2026-04-24) ---
        # Purpose: Pull cosmetics_enabled in the same fresh-fetch query so the
        # cosmetic overlay below uses authoritative DB state (the Pet cache
        # doesn't track this column).
        fresh = await _db_fetch(self.bot,
            "SELECT active_gameboy_skin_id, active_room_id, cosmetics_enabled FROM lg_pets WHERE userid = %s",
            pet.userid)
        if fresh:
            active_skin_id = fresh[0]['active_gameboy_skin_id']
            active_room_id = fresh[0]['active_room_id']
            cosmetics_enabled = fresh[0].get('cosmetics_enabled')
            if cosmetics_enabled is None:
                cosmetics_enabled = True
        else:
            active_skin_id = pet.active_gameboy_skin_id
            active_room_id = pet.active_room_id
            cosmetics_enabled = bool(getattr(pet, 'cosmetics_enabled', True))
        # --- END AI-MODIFIED ---

        room = await self.data.Room.fetch(active_room_id) if active_room_id else None
        room_prefix = room.asset_prefix if room else "rooms/default"

        skin = await self.data.GameboySkin.fetch(active_skin_id) if active_skin_id else None
        gameboy_skin = skin.asset_path if skin else "gameboy/frames/gameboy-basic-01.png"
        # --- END AI-MODIFIED ---

        expr_map = {
            LGExpression.DEFAULT: 'default', LGExpression.HAPPY: 'happy',
            LGExpression.SAD: 'sad', LGExpression.EATING: 'eating',
            LGExpression.SICK: 'sick', LGExpression.SLEEPING: 'sleeping',
        }

        # --- AI-REPLACED (2026-03-20) ---
        # Reason: Show gold + gems (both global) instead of gold + server coins
        # What the new code does better: Queries both gold and gems from user_config in one query
        # --- Original code (commented out for rollback) ---
        # gold = 0
        # try:
        #     rows = await _db_fetch(self.bot,
        #         "SELECT gold FROM user_config WHERE userid = %s", pet.userid
        #     )
        #     if rows:
        #         gold = rows[0]['gold'] or 0
        # except Exception:
        #     pass
        #
        # server_coins = 0
        # if guild:
        #     try:
        #         rows = await _db_fetch(self.bot,
        #             "SELECT coins FROM members WHERE guildid = %s AND userid = %s",
        #             guild.id, pet.userid
        #         )
        #         if rows:
        #             server_coins = rows[0]['coins'] or 0
        #     except Exception:
        #         pass
        # --- End original code ---
        gold = 0
        gems = 0
        try:
            rows = await _db_fetch(self.bot,
                "SELECT gold, gems FROM user_config WHERE userid = %s", pet.userid
            )
            if rows:
                gold = rows[0]['gold'] or 0
                gems = rows[0]['gems'] or 0
        except Exception:
            pass
        # --- END AI-REPLACED ---

        # --- AI-MODIFIED (2026-03-19) ---
        # Purpose: Fix enum handling for furniture slots (same pattern as equipment fix)
        room_furniture = {}
        try:
            furn_rows = await _db_fetch(self.bot,
                "SELECT slot, asset_path FROM lg_user_furniture WHERE userid = %s",
                pet.userid
            )
            for row in (furn_rows or []):
                raw_slot = row['slot']
                slot_str = raw_slot.value if hasattr(raw_slot, 'value') else str(raw_slot)
                # --- AI-MODIFIED (2026-03-24) ---
                # Purpose: Normalize furniture asset paths that are bare filenames
                # (e.g. "royalbed_02.png") to full paths ("rooms/furniture/royalbed_02.png").
                # The website already does this; without it the bot silently skips the layer.
                path = row['asset_path']
                if path and not path.startswith("rooms/"):
                    path = f"rooms/furniture/{path}"
                room_furniture[slot_str] = path
                # --- END AI-MODIFIED ---
        except Exception:
            logger.exception("Failed to load furniture for uid=%s", pet.userid)
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-03-19) ---
        # Purpose: Fix enum handling -- row['slot'] may be a Python Enum object from psycopg,
        # not a plain string, so convert to string before slot_map lookup
        equipped = {}
        try:
            eq_rows = await _db_fetch(self.bot,
                """SELECT e.slot, i.asset_path FROM lg_pet_equipment e
                   JOIN lg_items i ON e.itemid = i.itemid
                   WHERE e.userid = %s""",
                pet.userid
            )
            slot_map = {'HEAD': 'head', 'FACE': 'face', 'BODY': 'body', 'BACK': 'back', 'FEET': 'feet'}
            for row in (eq_rows or []):
                raw_slot = row['slot']
                slot_str = raw_slot.value if hasattr(raw_slot, 'value') else str(raw_slot)
                s = slot_map.get(slot_str, slot_str.lower())
                equipped[s] = f"equipment/{row['asset_path']}"
            logger.info("[EQUIP] Loaded equipment for uid=%s: %s", pet.userid, equipped)
        except Exception:
            logger.exception("Failed to load equipment for uid=%s", pet.userid)
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-04-24) ---
        # Purpose: Cosmetic overlay layer. After loading the real equipment
        # (which drives stats), overlay any rows from lg_pet_cosmetics on top
        # per slot. This is a VISUAL-ONLY swap -- bonuses still come from
        # lg_pet_equipment via calc_equipment_bonus in gameplay.py.
        #
        # Honors the per-pet cosmetics_enabled toggle (loaded above with the
        # fresh DB read): when FALSE the cosmetics rows are kept in the DB
        # but ignored here, so the user sees their "true equipment view"
        # without losing their picks.
        if cosmetics_enabled:
            try:
                cos_rows = await _db_fetch(self.bot,
                    """SELECT c.slot, i.asset_path FROM lg_pet_cosmetics c
                       JOIN lg_items i ON c.itemid = i.itemid
                       WHERE c.userid = %s""",
                    pet.userid
                )
                slot_map_cos = {'HEAD': 'head', 'FACE': 'face', 'BODY': 'body', 'BACK': 'back', 'FEET': 'feet'}
                for row in (cos_rows or []):
                    raw_slot = row['slot']
                    slot_str = raw_slot.value if hasattr(raw_slot, 'value') else str(raw_slot)
                    s = slot_map_cos.get(slot_str, slot_str.lower())
                    equipped[s] = f"equipment/{row['asset_path']}"
                if cos_rows:
                    logger.info("[COSMETIC] Overlay applied for uid=%s: %s slots overridden",
                                pet.userid, len(cos_rows))
            except Exception:
                logger.exception("Failed to load cosmetics for uid=%s", pet.userid)
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-03-16) ---
        # Purpose: Fetch room layout from lg_room_layout for custom positions,
        #          flips, layer order, and equipment order set via the website editor
        room_layout = {}
        try:
            layout_rows = await _db_fetch(self.bot,
                "SELECT layout FROM lg_room_layout WHERE userid = %s",
                pet.userid
            )
            if layout_rows and layout_rows[0].get('layout'):
                room_layout = layout_rows[0]['layout']
                if isinstance(room_layout, str):
                    import json
                    room_layout = json.loads(room_layout)
        except Exception:
            pass
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-03-20) ---
        # Purpose: Use lg_guild_display_name from guild config if set, else Discord guild name
        guild_name = ""
        if guild:
            try:
                lg_conf = await self._get_guild_lg_config(guild.id)
                custom_name = lg_conf.get('lg_guild_display_name')
                guild_name = custom_name if custom_name else guild.name[:12]
            except Exception:
                guild_name = guild.name[:12]
        # --- END AI-MODIFIED ---

        return PetState(
            pet_name=pet.pet_name or "Leo",
            guild_name=guild_name,
            level=pet.level or 1,
            food=pet.food, bath=pet.bath, sleep=pet.sleep, life=pet.life,
            gold=gold, gems=gems,
            expression=expr_map.get(pet.expression, 'default'),
            room_prefix=room_prefix,
            room_furniture=room_furniture,
            equipped_items=equipped,
            gameboy_skin=gameboy_skin,
            # --- AI-MODIFIED (2026-03-16) ---
            # Purpose: Pass room layout to PetState for custom rendering
            room_layout=room_layout,
            # --- END AI-MODIFIED ---
        )

    # ---- Show pet ----

    # --- AI-MODIFIED (2026-03-15) ---
    # Purpose: Read fullscreen_mode from DB and use appropriate renderer
    # --- AI-REPLACED (2026-03-19) ---
    # Reason: Stat redesign -- show mood + multiplier instead of life bar
    # What the new code does better: Shows derived mood with multiplier indicator,
    #   3 need bars (food/bath/sleep), and next decay countdown
    # --- Original code (commented out for rollback) ---
    # def _build_stats_text(self, state, pet, user_id, bonus_text=''):
    #     bar_life = "+" * state.life + "-" * (8 - state.life)
    #     text = f"{e_heart} Life `[{bar_life}]` | {e_steak} Food `[{bar_food}]`\n"
    #           f"{e_sleep} Sleep `[{bar_sleep}]` | {e_soap} Bath `[{bar_bath}]`"
    # --- End original code ---
    def _build_stats_text(self, state: PetState, pet, user_id: int,
                          bonus_text: str = '',
                          farm_line: str = '',
                          include_beta: bool = False,
                          bonus_section_header: bool = False) -> str:
        from .gameplay import xp_for_level
        xp_needed = xp_for_level(state.level)
        xp_current = pet.xp or 0
        bar_food = "+" * state.food + "-" * (8 - state.food)
        bar_bath = "+" * state.bath + "-" * (8 - state.bath)
        bar_sleep = "+" * state.sleep + "-" * (8 - state.sleep)
        e_coin = _lg_emoji('lg_coin', '\U0001F4B0')
        e_xp = _lg_emoji('lg_xp', '\u2B50')
        e_steak = _lg_emoji('lg_steak', '\U0001F356')
        e_sleep = _lg_emoji('lg_sleep', '\U0001F4A4')
        e_soap = _lg_emoji('lg_soap', '\U0001F9FC')

        mood = calc_mood(state.food, state.bath, state.sleep)
        mood_label = MOOD_LABELS.get(mood, 'Okay')
        mood_emoji = MOOD_EMOJI.get(mood_label, '\U0001F610')
        mood_mult = MOOD_MULTIPLIERS.get(mood, 1.0)
        if mood_mult != 1.0:
            mult_text = str(_p(
                'embed:pet_card|mood_mult',
                " \u2014 **{mult:.2f}x** Gold & XP"
            )).format(mult=mood_mult)
        else:
            mult_text = ""

        last_decay = pet.last_decay_at
        if last_decay and hasattr(last_decay, 'tzinfo'):
            if last_decay.tzinfo is None:
                last_decay = last_decay.replace(tzinfo=timezone.utc)
            next_decay = last_decay.timestamp() + NEEDS_DECAY_INTERVAL_HOURS * 3600
            next_decay_rel = f"<t:{int(next_decay)}:R>"
        else:
            next_decay_rel = str(_p('embed:pet_card|decay_soon', "soon"))

        hdr = str(_p(
            'embed:pet_card|header',
            "**{pet_name}'s LionGotchi**\n\n"
        )).format(pet_name=state.pet_name)
        lvl = str(_p(
            'embed:pet_card|level_line',
            "{e_xp} **Level {level}** ({xp_current}/{xp_needed} XP)\n"
        )).format(
            e_xp=e_xp, level=state.level,
            xp_current=xp_current, xp_needed=xp_needed,
        )
        gg = str(_p(
            'embed:pet_card|gold_gems',
            "{e_coin} Gold: **{gold:,}** | {gem_emoji} Gems: **{gems:,}**\n\n"
        )).format(
            e_coin=e_coin, gold=state.gold, gem_emoji='\U0001f48e', gems=state.gems,
        )
        mood_ln = str(_p(
            'embed:pet_card|mood_line',
            "{mood_emoji} Mood: **{mood_label}**{mult_text}\n"
        )).format(
            mood_emoji=mood_emoji, mood_label=mood_label, mult_text=mult_text,
        )
        needs = str(_p(
            'embed:pet_card|needs_row',
            "{e_steak} Hunger `[{bar_food}]` | {e_soap} Clean `[{bar_bath}]` | "
            "{e_sleep} Energy `[{bar_sleep}]`\n"
        )).format(
            e_steak=e_steak, bar_food=bar_food, e_soap=e_soap, bar_bath=bar_bath,
            e_sleep=e_sleep, bar_sleep=bar_sleep,
        )
        decay_ln = str(_p(
            'embed:pet_card|next_decay',
            "-# Next decay {when}"
        )).format(when=next_decay_rel)

        text = hdr + lvl + gg + mood_ln + needs + decay_ln
        if farm_line:
            text += "\n\n" + farm_line
        if bonus_text:
            if bonus_section_header:
                text += str(_p(
                    'embed:pet_card|active_bonuses_block',
                    "\n\n\u2500\u2500\u2500 **Active Bonuses** \u2500\u2500\u2500\n{bonus}"
                )).format(bonus=bonus_text)
            else:
                text += f"\n\n{bonus_text}"
        text += str(_p(
            'embed:pet_card|artist_note',
            "\n\n-# *All LionGotchi art is hand-drawn by real humans \u2014 "
            "1,000+ items over 12 months of work, not AI. "
            "Subscriptions & gems support our artists.*"
        ))
        if include_beta:
            text += str(_p(
                'embed:pet_card|beta_note',
                "\n-# \U0001F41B *LionGotchi is in Beta \u2014 help us improve! "
                "Click \"Report a Bug\" below.*"
            ))
        return text
    # --- END AI-REPLACED ---

    async def _show_pet(self, interaction: discord.Interaction, edit: bool = False):
        # --- AI-REPLACED (2026-03-20) ---
        # Reason: Visual onboarding with GIF previews for first-time users
        # What the new code does better: Shows animated GIF alongside the tutorial embed
        # --- Original code (commented out for rollback) ---
        # existing = await self.data.Pet.fetch(interaction.user.id)
        # if existing is None:
        #     view = OnboardingView(self, interaction.user.id)
        #     await interaction.response.send_message(embed=view._build_embed(), view=view, ephemeral=True)
        #     return
        # --- End original code ---
        existing = await self.data.Pet.fetch(interaction.user.id)
        is_onboarding = existing is None or (existing and getattr(existing, 'data', None) is None)
        # --- AI-MODIFIED (2026-03-24) ---
        # Purpose: Defer interaction to avoid Discord's 3-second timeout on slow DB/render
        already_responded = interaction.response.is_done()
        if not already_responded:
            _is_modal = interaction.type == discord.InteractionType.modal_submit
            if edit and _is_modal:
                pass
            elif edit:
                await interaction.response.defer()
                already_responded = True
            elif is_onboarding:
                await interaction.response.defer(ephemeral=True)
                already_responded = True
            else:
                await interaction.response.defer()
                already_responded = True
        # --- END AI-MODIFIED ---
        if is_onboarding:
            view = OnboardingView(self, interaction.user.id)
            await self._add_vote_btn(view, interaction.user.id, interaction.guild_id)
            embed, gif_file = await view._build_embed_and_file()
            if edit:
                attachments = [gif_file] if gif_file else []
                if already_responded:
                    await interaction.edit_original_response(
                        content=None, embed=embed,
                        attachments=attachments, view=view
                    )
                else:
                    await interaction.response.edit_message(
                        content=None, embed=embed,
                        attachments=attachments, view=view
                    )
            else:
                if already_responded:
                    kwargs = {'content': None, 'embed': embed, 'view': view}
                    if gif_file:
                        kwargs['attachments'] = [gif_file]
                    await interaction.edit_original_response(**kwargs)
                else:
                    kwargs = {'embed': embed, 'view': view, 'ephemeral': True}
                    if gif_file:
                        kwargs['file'] = gif_file
                    await interaction.response.send_message(**kwargs)
            return
        # --- END AI-REPLACED ---
        pet = await self._get_or_create_pet(interaction.user.id)
        # --- AI-MODIFIED (2026-03-26) ---
        # Purpose: Refresh pet data from DB to pick up changes made by the website or other processes
        if pet is not None and pet.data is not None:
            await pet.refresh()
        # --- END AI-MODIFIED ---
        pet = await self._apply_decay(pet)
        state = await self._build_pet_state(pet, interaction.guild)
        self._last_pet_name = state.pet_name

        fullscreen = False
        try:
            rows = await _db_fetch(self.bot,
                "SELECT fullscreen_mode FROM lg_pets WHERE userid = %s",
                interaction.user.id)
            if rows and rows[0]['fullscreen_mode']:
                fullscreen = True
        except Exception:
            pass

        if fullscreen:
            gif_bytes = await asyncio.to_thread(render_fullscreen_frame, state)
        else:
            gif_bytes = await asyncio.to_thread(render_gameboy_frame, state)
        file = discord.File(BytesIO(gif_bytes), filename="liongotchi.gif")
        view = PetView(self, interaction.user.id, interaction.guild_id or 0, fullscreen=fullscreen)
        # --- AI-MODIFIED (2026-03-19) ---
        await self._add_vote_btn(view, interaction.user.id, interaction.guild_id)
        # --- END AI-MODIFIED ---
    # --- END AI-MODIFIED ---

        # --- AI-REPLACED (2026-03-19) ---
        # Reason: Stat redesign -- show mood + multiplier instead of life, 3 need bars
        # What the new code does better: Mood-driven display with multiplier, decay countdown
        # --- Original code (commented out for rollback) ---
        # bar_life = "+" * state.life + "-" * (8 - state.life)
        # stats_text = f"{e_heart} Life `[{bar_life}]` | {e_steak} Food `[{bar_food}]`\n"
        #              f"{e_sleep} Sleep `[{bar_sleep}]` | {e_soap} Bath `[{bar_bath}]`"
        # --- End original code ---
        farm_planted = 0
        farm_ready = 0
        try:
            farm_rows = await _db_fetch(self.bot,
                "SELECT growth_stage, dead, seed_id FROM lg_user_farm WHERE userid = %s",
                interaction.user.id
            )
            for r in (farm_rows or []):
                if r['seed_id']:
                    farm_planted += 1
                    if r['growth_stage'] >= 5 and not r['dead']:
                        farm_ready += 1
        except Exception:
            pass

        from .gameplay import calc_all_bonuses, format_bonus_summary
        bonus_text = ""
        try:
            user_tier, server_premium = await self._get_premium_context(
                interaction.user.id, interaction.guild_id)
            bonuses = await calc_all_bonuses(self.bot, interaction.user.id,
                                              user_tier=user_tier, server_premium=server_premium)
            bonus_text = format_bonus_summary(bonuses) or ""
        except Exception:
            pass

        farm_line = str(_p(
            'embed:pet_card|farm_planted',
            "\U0001F33F Farm: **{planted}**/15 planted"
        )).format(planted=farm_planted)
        if farm_ready:
            farm_line += str(_p(
                'embed:pet_card|farm_ready',
                " (**{ready}** ready to harvest!)"
            )).format(ready=farm_ready)

        stats_text = self._build_stats_text(
            state, pet, interaction.user.id,
            bonus_text=bonus_text,
            farm_line=farm_line,
            include_beta=True,
            bonus_section_header=bool(bonus_text),
        )
        # --- END AI-REPLACED ---

        # --- AI-MODIFIED (2026-03-24) ---
        # Purpose: Use deferred-aware response methods to avoid timeout
        if edit:
            if already_responded:
                await interaction.edit_original_response(
                    content=stats_text, embed=None, attachments=[file], view=view
                )
            else:
                await interaction.response.edit_message(
                    content=stats_text, embed=None, attachments=[file], view=view
                )
        else:
            if already_responded:
                await interaction.edit_original_response(
                    content=stats_text, embed=None, attachments=[file], view=view
                )
            else:
                await interaction.response.send_message(
                    content=stats_text, file=file, view=view
                )
            # --- END AI-MODIFIED ---
            if random.random() < 0.2:
                try:
                    tip_view = discord.ui.View()
                    tip_view.add_item(discord.ui.Button(
                        label=_p('ui:pet|button:visit_website|label', "Visit Website"),
                        url=f"{WEBSITE_URL}/pet",
                        style=discord.ButtonStyle.link
                    ))
                    await interaction.followup.send(
                        content=str(_p(
                            'tip:website_promo',
                            "**New in 2026!** Customize your room on our website "
                            "\u2014 drag and drop furniture, resize items, and "
                            "browse our full catalog!\n\n"
                            "We're back with a huge update and would love your feedback!"
                        )),
                        ephemeral=True,
                        view=tip_view
                    )
                except Exception:
                    pass
        # --- END AI-REPLACED ---

    # ---- Care actions ----

    # --- AI-REPLACED (2026-03-19) ---
    # Reason: Stat redesign -- no more life updates, mood is derived
    # What the new code does better: Simpler care action, no life tracking
    # --- Original code (commented out for rollback) ---
    # async def _feed_pet(self, interaction):
    #     new_life = min(8, pet.life + 1) if pet.food <= 2 else pet.life
    #     await _db_exec(self.bot, "UPDATE lg_pets SET food = %s, life = %s, expression = %s ...")
    # --- End original code ---
    async def _feed_pet(self, interaction: discord.Interaction):
        now = datetime.now(timezone.utc)
        # --- AI-REPLACED (2026-05-15) ---
        # Reason: One-click fill-to-max. Cooldown removed -- once the stat is at 8, repeat
        #   clicks within the same day are no-ops anyway. Also apply pending decay first and
        #   bump last_decay_at so bot and website behave identically across a care action.
        # What the new code does better: Restores Fainted pets in one click instead of forcing
        #   users to wait 2 minutes between four clicks per stat.
        # --- Original code (commented out for rollback) ---
        # last = self._feed_cooldowns.get(interaction.user.id)
        # if last and (now - last).total_seconds() < FEED_COOLDOWN_SECONDS:
        #     remaining = FEED_COOLDOWN_SECONDS - int((now - last).total_seconds())
        #     await interaction.response.send_message(
        #         str(_p(
        #             'error:feed|cooldown',
        #             "Your pet just ate! Try again in {remaining}s."
        #         )).format(remaining=remaining),
        #         ephemeral=True)
        #     return
        # pet = await self._get_or_create_pet(interaction.user.id)
        # new_food = min(8, pet.food + 2)
        # await _db_exec(self.bot,
        #     "UPDATE lg_pets SET food = %s, expression = %s WHERE userid = %s",
        #     new_food, 'EATING', interaction.user.id
        # )
        # --- End original code ---
        pet = await self._get_or_create_pet(interaction.user.id)
        pet = await self._apply_decay(pet)
        new_food = 8
        await _db_exec(self.bot,
            "UPDATE lg_pets SET food = %s, expression = %s, last_decay_at = %s WHERE userid = %s",
            new_food, 'EATING', now, interaction.user.id
        )
        # --- END AI-REPLACED ---
        # --- AI-MODIFIED (2026-03-26) ---
        # Purpose: Sync in-memory cache after DB update so display reflects the change
        if pet.data is not None:
            pet.data['food'] = new_food
            # --- AI-MODIFIED (2026-05-15) ---
            # Purpose: Keep last_decay_at in cache aligned with the DB write above.
            pet.data['last_decay_at'] = now
            # --- END AI-MODIFIED ---
        # --- END AI-MODIFIED ---
        # --- AI-MODIFIED (2026-04-03) ---
        # Purpose: Read fullscreen_mode so care actions restore the correct view mode
        fullscreen = False
        try:
            _fs_rows = await _db_fetch(self.bot,
                "SELECT fullscreen_mode FROM lg_pets WHERE userid = %s",
                interaction.user.id)
            if _fs_rows and _fs_rows[0]['fullscreen_mode']:
                fullscreen = True
        except Exception:
            pass
        # --- END AI-MODIFIED ---
        self._feed_cooldowns[interaction.user.id] = now
        state = await self._build_pet_state(pet, interaction.guild)
        gif_bytes = await asyncio.to_thread(render_action_frame, state, 'feed')
        file = discord.File(BytesIO(gif_bytes), filename="feed.gif")
        view = PetView(self, interaction.user.id, interaction.guild_id or 0, fullscreen=fullscreen)
        await interaction.response.edit_message(
            content=str(_p('pet:action:feed', "\U0001F356 **nom nom nom!**")),
            embed=None, attachments=[file], view=view
        )
        await asyncio.sleep(3)
        await _db_exec(self.bot,
            "UPDATE lg_pets SET expression = %s WHERE userid = %s",
            'DEFAULT', interaction.user.id
        )
        try:
            pet2 = await self._get_or_create_pet(interaction.user.id)
            state2 = await self._build_pet_state(pet2, interaction.guild)
            gif2 = await asyncio.to_thread(
                render_fullscreen_frame if fullscreen else render_gameboy_frame, state2)
            file2 = discord.File(BytesIO(gif2), filename="liongotchi.gif")
            view2 = PetView(self, interaction.user.id, interaction.guild_id or 0, fullscreen=fullscreen)
            # --- AI-MODIFIED (2026-03-17) ---
            # Purpose: Pass bonus text to _build_stats_text for care action revert
            from .gameplay import calc_all_bonuses, format_bonus_summary
            ut, sp = await self._get_premium_context(interaction.user.id, interaction.guild_id)
            b = await calc_all_bonuses(self.bot, interaction.user.id, user_tier=ut, server_premium=sp)
            bt = format_bonus_summary(b)
            # --- END AI-MODIFIED ---
            await interaction.edit_original_response(
                content=self._build_stats_text(state2, pet2, interaction.user.id, bonus_text=bt),
                attachments=[file2], view=view2
            )
        except Exception:
            pass
    # --- END AI-MODIFIED ---

    # --- AI-REPLACED (2026-03-19) ---
    # Reason: Stat redesign -- no more life updates, mood is derived
    # What the new code does better: Simpler care action, no life tracking
    # --- Original code (commented out for rollback) ---
    # async def _bathe_pet(self, interaction):
    #     new_life = min(8, pet.life + 1) if pet.bath <= 2 else pet.life
    #     await _db_exec(self.bot, "UPDATE lg_pets SET bath = %s, life = %s, expression = %s ...")
    # --- End original code ---
    async def _bathe_pet(self, interaction: discord.Interaction):
        now = datetime.now(timezone.utc)
        # --- AI-REPLACED (2026-05-15) ---
        # Reason: One-click fill-to-max + apply pending decay, mirroring _feed_pet.
        # --- Original code (commented out for rollback) ---
        # last = self._bathe_cooldowns.get(interaction.user.id)
        # if last and (now - last).total_seconds() < BATHE_COOLDOWN_SECONDS:
        #     remaining = BATHE_COOLDOWN_SECONDS - int((now - last).total_seconds())
        #     await interaction.response.send_message(
        #         str(_p(
        #             'error:bathe|cooldown',
        #             "Your pet is already clean! Try again in {remaining}s."
        #         )).format(remaining=remaining),
        #         ephemeral=True)
        #     return
        # pet = await self._get_or_create_pet(interaction.user.id)
        # new_bath = min(8, pet.bath + 2)
        # await _db_exec(self.bot,
        #     "UPDATE lg_pets SET bath = %s, expression = %s WHERE userid = %s",
        #     new_bath, 'HAPPY', interaction.user.id
        # )
        # --- End original code ---
        pet = await self._get_or_create_pet(interaction.user.id)
        pet = await self._apply_decay(pet)
        new_bath = 8
        await _db_exec(self.bot,
            "UPDATE lg_pets SET bath = %s, expression = %s, last_decay_at = %s WHERE userid = %s",
            new_bath, 'HAPPY', now, interaction.user.id
        )
        # --- END AI-REPLACED ---
        # --- AI-MODIFIED (2026-03-26) ---
        # Purpose: Sync in-memory cache after DB update so display reflects the change
        if pet.data is not None:
            pet.data['bath'] = new_bath
            # --- AI-MODIFIED (2026-05-15) ---
            # Purpose: Keep last_decay_at in cache aligned with the DB write above.
            pet.data['last_decay_at'] = now
            # --- END AI-MODIFIED ---
        # --- END AI-MODIFIED ---
        # --- AI-MODIFIED (2026-04-03) ---
        # Purpose: Read fullscreen_mode so care actions restore the correct view mode
        fullscreen = False
        try:
            _fs_rows = await _db_fetch(self.bot,
                "SELECT fullscreen_mode FROM lg_pets WHERE userid = %s",
                interaction.user.id)
            if _fs_rows and _fs_rows[0]['fullscreen_mode']:
                fullscreen = True
        except Exception:
            pass
        # --- END AI-MODIFIED ---
        self._bathe_cooldowns[interaction.user.id] = now
        state = await self._build_pet_state(pet, interaction.guild)
        gif_bytes = await asyncio.to_thread(render_action_frame, state, 'bathe')
        file = discord.File(BytesIO(gif_bytes), filename="bathe.gif")
        view = PetView(self, interaction.user.id, interaction.guild_id or 0, fullscreen=fullscreen)
        await interaction.response.edit_message(
            content=str(_p('pet:action:bathe', "\U0001F9FC **splashhh!**")),
            embed=None, attachments=[file], view=view
        )
        await asyncio.sleep(3)
        await _db_exec(self.bot,
            "UPDATE lg_pets SET expression = %s WHERE userid = %s",
            'DEFAULT', interaction.user.id
        )
        try:
            pet2 = await self._get_or_create_pet(interaction.user.id)
            state2 = await self._build_pet_state(pet2, interaction.guild)
            gif2 = await asyncio.to_thread(
                render_fullscreen_frame if fullscreen else render_gameboy_frame, state2)
            file2 = discord.File(BytesIO(gif2), filename="liongotchi.gif")
            view2 = PetView(self, interaction.user.id, interaction.guild_id or 0, fullscreen=fullscreen)
            # --- AI-MODIFIED (2026-03-17) ---
            # Purpose: Pass bonus text to _build_stats_text for care action revert
            from .gameplay import calc_all_bonuses, format_bonus_summary
            ut, sp = await self._get_premium_context(interaction.user.id, interaction.guild_id)
            b = await calc_all_bonuses(self.bot, interaction.user.id, user_tier=ut, server_premium=sp)
            bt = format_bonus_summary(b)
            # --- END AI-MODIFIED ---
            await interaction.edit_original_response(
                content=self._build_stats_text(state2, pet2, interaction.user.id, bonus_text=bt),
                attachments=[file2], view=view2
            )
        except Exception:
            pass
    # --- END AI-MODIFIED ---

    # --- AI-REPLACED (2026-03-16) ---
    # Reason: Sleep button now toggles between sleeping and waking up
    # What the new code does better: If pet is already sleeping, wakes it up (sets DEFAULT)
    # --- Original code (commented out for rollback) ---
    # async def _sleep_pet(self, interaction: discord.Interaction):
    #     pet = await self._get_or_create_pet(interaction.user.id)
    #     new_sleep = min(8, pet.sleep + 3)
    #     new_life = min(8, pet.life + 1) if pet.sleep <= 2 else pet.life
    #     await _db_exec(self.bot,
    #         "UPDATE lg_pets SET sleep = %s, life = %s, expression = %s WHERE userid = %s",
    #         new_sleep, new_life, 'SLEEPING', interaction.user.id
    #     )
    #     await self._show_pet(interaction, edit=True)
    # --- End original code ---
    # --- AI-REPLACED (2026-03-19) ---
    # Reason: Stat redesign -- sleep is now consistent with feed/bathe (+2, 2min cooldown)
    # What the new code does better: No more toggle, consistent behavior across all 3 care actions
    # --- Original code (commented out for rollback) ---
    # async def _sleep_pet(self, interaction):
    #     is_sleeping = getattr(pet, 'expression', None) in (LGExpression.SLEEPING, 'SLEEPING')
    #     if is_sleeping: action = 'wake' else: new_sleep = min(8, pet.sleep + 3) ...
    # --- End original code ---
    async def _sleep_pet(self, interaction: discord.Interaction):
        now = datetime.now(timezone.utc)
        # --- AI-REPLACED (2026-05-15) ---
        # Reason: One-click fill-to-max + apply pending decay, mirroring _feed_pet.
        # --- Original code (commented out for rollback) ---
        # last = self._sleep_cooldowns.get(interaction.user.id)
        # if last and (now - last).total_seconds() < SLEEP_COOLDOWN_SECONDS:
        #     remaining = SLEEP_COOLDOWN_SECONDS - int((now - last).total_seconds())
        #     await interaction.response.send_message(
        #         str(_p(
        #             'error:sleep|cooldown',
        #             "Your pet just rested! Try again in {remaining}s."
        #         )).format(remaining=remaining),
        #         ephemeral=True)
        #     return
        # pet = await self._get_or_create_pet(interaction.user.id)
        # new_sleep = min(8, pet.sleep + 2)
        # await _db_exec(self.bot,
        #     "UPDATE lg_pets SET sleep = %s, expression = %s WHERE userid = %s",
        #     new_sleep, 'SLEEPING', interaction.user.id
        # )
        # --- End original code ---
        pet = await self._get_or_create_pet(interaction.user.id)
        pet = await self._apply_decay(pet)
        new_sleep = 8
        await _db_exec(self.bot,
            "UPDATE lg_pets SET sleep = %s, expression = %s, last_decay_at = %s WHERE userid = %s",
            new_sleep, 'SLEEPING', now, interaction.user.id
        )
        # --- END AI-REPLACED ---
        # --- AI-MODIFIED (2026-03-26) ---
        # Purpose: Sync in-memory cache after DB update so display reflects the change
        if pet.data is not None:
            pet.data['sleep'] = new_sleep
            # --- AI-MODIFIED (2026-05-15) ---
            # Purpose: Keep last_decay_at in cache aligned with the DB write above.
            pet.data['last_decay_at'] = now
            # --- END AI-MODIFIED ---
        # --- END AI-MODIFIED ---
        # --- AI-MODIFIED (2026-04-03) ---
        # Purpose: Read fullscreen_mode so care actions restore the correct view mode
        fullscreen = False
        try:
            _fs_rows = await _db_fetch(self.bot,
                "SELECT fullscreen_mode FROM lg_pets WHERE userid = %s",
                interaction.user.id)
            if _fs_rows and _fs_rows[0]['fullscreen_mode']:
                fullscreen = True
        except Exception:
            pass
        # --- END AI-MODIFIED ---
        self._sleep_cooldowns[interaction.user.id] = now
        state = await self._build_pet_state(pet, interaction.guild)
        gif_bytes = await asyncio.to_thread(render_action_frame, state, 'sleep')
        file = discord.File(BytesIO(gif_bytes), filename="sleep.gif")
        view = PetView(self, interaction.user.id, interaction.guild_id or 0, fullscreen=fullscreen)
        await interaction.response.edit_message(
            content=str(_p('pet:action:sleep', "\U0001F4A4 **Zzz...**")),
            embed=None, attachments=[file], view=view
        )
        await asyncio.sleep(3)
        await _db_exec(self.bot,
            "UPDATE lg_pets SET expression = %s WHERE userid = %s",
            'DEFAULT', interaction.user.id
        )
        try:
            pet2 = await self._get_or_create_pet(interaction.user.id)
            state2 = await self._build_pet_state(pet2, interaction.guild)
            gif2 = await asyncio.to_thread(
                render_fullscreen_frame if fullscreen else render_gameboy_frame, state2)
            file2 = discord.File(BytesIO(gif2), filename="liongotchi.gif")
            view2 = PetView(self, interaction.user.id, interaction.guild_id or 0, fullscreen=fullscreen)
            from .gameplay import calc_all_bonuses, format_bonus_summary
            ut, sp = await self._get_premium_context(interaction.user.id, interaction.guild_id)
            b = await calc_all_bonuses(self.bot, interaction.user.id, user_tier=ut, server_premium=sp)
            bt = format_bonus_summary(b)
            await interaction.edit_original_response(
                content=self._build_stats_text(state2, pet2, interaction.user.id, bonus_text=bt),
                attachments=[file2], view=view2
            )
        except Exception:
            pass
    # --- END AI-REPLACED ---

    # ---- Activity listeners (Gold, XP, needs, drops) ----

    # --- AI-MODIFIED (2026-03-15) ---
    # Purpose: Accumulate messages for responsive farm growth (independent of text tracker batching)
    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: Also check for item drops every 5 messages for near-instant feedback
    DROP_MSG_THRESHOLD = 5

    @LionCog.listener('on_message')
    async def on_message_farm(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        userid = message.author.id

        # --- AI-MODIFIED (2026-03-20) ---
        # Purpose: Check lg_enabled and lg_activity_role before processing text activity
        guildid = message.guild.id
        lg_conf = await self._get_guild_lg_config(guildid)
        if not lg_conf.get('lg_enabled', True):
            return
        activity_role_id = lg_conf.get('lg_activity_role')
        if activity_role_id and message.author.get_role(activity_role_id) is None:
            return
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-03-17) ---
        # Purpose: Anti-cheat per-message cooldown -- only count 1 msg per 10s for farm growth
        if not self._msg_on_cooldown(userid):
            self._farm_msg_counts[userid] = self._farm_msg_counts.get(userid, 0) + 1
        # --- END AI-MODIFIED ---

        self._drop_msg_counts[userid] = self._drop_msg_counts.get(userid, 0) + 1
        if self._drop_msg_counts[userid] >= self.DROP_MSG_THRESHOLD:
            self._drop_msg_counts[userid] = 0
            asyncio.create_task(self._check_message_drop(userid, message.guild.id, message.channel))
    # --- END AI-MODIFIED ---

    # --- AI-REPLACED (2026-03-16) ---
    # Reason: Materials removed; use try_item_drop for equipment/scroll drops
    # What the new code does better: Drops equipment/scrolls instead of materials
    # --- Original code (commented out for rollback) ---
    # materials = await try_material_drop(self.bot, userid, 1.0, ...)
    # materials = await try_material_drop(self.bot, userid, MATERIAL_DROP_CHANCE_TEXT, ...)
    # --- End original code ---
    async def _check_message_drop(self, userid: int, guildid: int, channel):
        try:
            is_first_encounter = userid not in self._first_encounter_sent

            pet = await self.data.Pet.fetch(userid)
            if pet is None:
                if is_first_encounter:
                    self._first_encounter_sent.add(userid)
                    await self._send_first_encounter(userid, guildid, channel)
                # --- AI-MODIFIED (2026-03-20) ---
                # Purpose: Respect lg_teaser_enabled guild setting
                elif random.random() < TEASER_CHANCE:
                    lg_conf = await self._get_guild_lg_config(guildid)
                    if lg_conf.get('lg_teaser_enabled', True):
                        drop_ch = await self._get_guild_drop_channel(guildid)
                        await self._send_teaser(userid, guildid, drop_ch)
                # --- END AI-MODIFIED ---
                return

            self._first_encounter_sent.add(userid)

            user_tier, server_premium = await self._get_premium_context(userid, guildid)

            is_first_drop = False
            if is_first_encounter:
                async with self.bot.db.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "SELECT COUNT(*) AS cnt FROM lg_user_inventory WHERE userid = %s AND source = 'DROP'",
                            [userid]
                        )
                        row = await cur.fetchone()
                        is_first_drop = (row['cnt'] == 0) if row else True

            # --- AI-MODIFIED (2026-03-17) ---
            # Purpose: Check daily drop cap before rolling (first drop always allowed)
            if not is_first_drop and not self._can_drop(userid):
                return
            # --- END AI-MODIFIED ---

            chance = 1.0 if is_first_drop else ITEM_DROP_CHANCE_TEXT

            # --- AI-MODIFIED (2026-03-24) ---
            # Purpose: Pass VC Study Streak quality boost + equipment drop bonus to text drops
            vc_boost, vc_tier, vc_daily_min = self._get_vc_rarity_boost(userid)
            from .gameplay import calc_equipment_bonus
            _, _, equip_drop = await calc_equipment_bonus(self.bot, userid)
            # --- END AI-MODIFIED ---

            if is_first_drop:
                drops = await try_item_drop(
                    self.bot, userid, 1.0,
                    user_tier=user_tier, server_premium=server_premium,
                    quality_boost=vc_boost,
                    equip_drop_bonus=equip_drop
                )
            else:
                # --- AI-MODIFIED (2026-03-24) ---
                # Purpose: Pass equipment drop bonus to text message drops
                drops = await try_item_drop(
                    self.bot, userid, ITEM_DROP_CHANCE_TEXT,
                    user_tier=user_tier, server_premium=server_premium,
                    quality_boost=vc_boost,
                    equip_drop_bonus=equip_drop
                )
                # --- END AI-MODIFIED ---

            if drops:
                # --- AI-MODIFIED (2026-03-17) ---
                # Purpose: Record drop for daily cap tracking
                self._record_drop(userid)
                # --- END AI-MODIFIED ---
                if is_first_drop:
                    await self._send_first_drop(userid, drops, guildid, channel)
                else:
                    drop_ch = await self._get_guild_drop_channel(guildid)
                    await self._send_drop_notification(userid, drops, guildid, drop_ch or channel,
                                                        vc_tier=vc_tier, vc_daily_min=vc_daily_min,
                                                        vc_boost=vc_boost)
        except Exception:
            logger.exception("Error in per-message drop check")
    # --- END AI-REPLACED ---

    # --- AI-REPLACED (2026-03-20) ---
    # Reason: Visual first encounter with GIF preview, social proof, and longer display time
    # What the new code does better: Shows an animated pet preview GIF, punchier FOMO-driven
    #   copy with pet count, 5-minute display time instead of 2 minutes
    # --- Original code (commented out for rollback) ---
    # async def _send_first_encounter(self, userid, guildid, channel):
    #     embed = Embed(title="You Found Something!", description="While you were chatting...")
    #     embed.set_footer(text=f"The more you study... {WEBSITE_URL}/pet")
    #     view = FirstEncounterView(self, userid)
    #     await target.send(content=f"<@{userid}>", embed=embed, view=view, delete_after=120)
    # --- End original code ---
    async def _send_first_encounter(self, userid: int, guildid: int, channel):
        """Send a compelling first-encounter message with GIF preview to a user without a pet."""
        # --- AI-MODIFIED (2026-03-21) ---
        # Purpose: Temporarily disable server-channel first encounter messages (users complained about spam)
        return
        # --- END AI-MODIFIED ---
        pet_count = getattr(self, '_cached_pet_count', None)
        social_line = ""
        if pet_count and pet_count > 100:
            social_line = str(_p(
                'embed:first_encounter|social',
                "\n\U0001F465 **{count:,} members** already have a LionGotchi!\n"
            )).format(count=pet_count)

        embed = discord.Embed(
            title=str(_p('embed:first_encounter|title', "\U0001F981 You Found Something!")),
            color=0xffd700,
            description=str(_p(
                'embed:first_encounter|desc',
                "While you were chatting, something caught your eye...\n\n"
                "\u2728 **Equipment and scrolls** drop while you're productive!\n"
                "Active members earn rare gear just by being productive.\n"
                "{social_line}\n"
                "\U0001F43E **Adopt a LionGotchi pet** to start collecting!\n"
                "\u2694\uFE0F Equipment with stat bonuses \u2022 "
                "\U0001F331 A farm to grow \u2022 "
                "\U0001F4B0 A marketplace to trade\n\n"
                "Type **`/pet`** or tap below to get started!"
            )).format(social_line=social_line),
        )
        embed.set_footer(text=str(_p(
            'embed:first_encounter|footer',
            "The more productive you are, the more you earn \u2022 {url}"
        )).format(url=f"{WEBSITE_URL}/pet"))

        gif_file = None
        try:
            gif_bytes = await self._onboarding_gifs.get('welcome')
            gif_file = discord.File(BytesIO(gif_bytes), filename="welcome.gif")
            embed.set_image(url="attachment://welcome.gif")
        except Exception:
            logger.debug("Failed to load welcome GIF for first encounter")

        view = FirstEncounterView(self, userid)

        drop_ch = await self._get_guild_drop_channel(guildid)
        lg_conf = await self._get_guild_lg_config(guildid)
        custom_delete = lg_conf.get('lg_drop_delete_after')
        target = drop_ch or channel
        if target:
            try:
                if drop_ch:
                    del_after = custom_delete
                else:
                    del_after = custom_delete if custom_delete else 300
                kwargs = {
                    'content': f"<@{userid}>",
                    'embed': embed,
                    'view': view,
                    'delete_after': del_after,
                }
                if gif_file:
                    kwargs['file'] = gif_file
                await target.send(**kwargs)
            except Exception:
                logger.exception(f"Failed to send first encounter to channel for {userid}")
    # --- END AI-REPLACED ---

    # --- AI-REPLACED (2026-04-07) ---
    # Reason: Add drop card image and item wiki link to first drop notification
    # What the new code does better: Generates a visual card for the first drop,
    #   passes itemid to FirstDropView for wiki link button
    # --- Original code (commented out for rollback) ---
    # async def _send_first_drop(self, userid, drops, guildid, channel):
    #     embed = discord.Embed(title="Your First Item Drop!", color=0xffd700)
    #     drop_lines = [f"{r_emoji} **{d['name']}**{cat_label} ({label})" for d in drops]
    #     embed.description = "Your pet found its very first item!\n\n" + drops + "\n\n..."
    #     embed.set_footer(text="Tip: ...")
    #     view = FirstDropView(self, userid)
    #     user.send(embed=embed, view=view)
    # --- End original code ---
    async def _send_first_drop(self, userid: int, drops: list[dict],
                                guildid: int, channel):
        """Send a special celebration for a pet owner's very first item drop."""
        from .item_renderer import render_drop_card

        embed = discord.Embed(
            title=str(_p('embed:first_drop|title', "\U0001F389 Your First Item Drop!")),
            color=0xffd700,
        )
        scroll_lbl = str(_p('embed:first_drop|label_scroll', "[Scroll]"))
        drop_lines = []
        for d in drops:
            rarity = _clean_rarity(d.get('rarity', 'COMMON'))
            r_emoji = RARITY_EMOJI.get(rarity, '\u26AA')
            label = RARITY_LABELS.get(rarity, rarity.title())
            cat = d.get('category', '')
            cat_label = f" [{cat.title()}]" if cat and cat != 'SCROLL' else (f" {scroll_lbl}" if cat == 'SCROLL' else "")
            drop_lines.append(f"{r_emoji} **{d['name']}**{cat_label} ({label})")
        drops_block = "\n".join(drop_lines)

        first_drop = drops[0] if drops else {}
        item_desc = first_drop.get('description', '')
        desc_line = f"\n> *{item_desc[:120]}*\n" if item_desc else "\n"

        embed.description = str(_p(
            'embed:first_drop|desc',
            "Your pet found its very first item!\n\n{drops}{desc_line}\n"
            "\u2694\uFE0F **What now?** Equipment boosts your gold and XP earnings.\n"
            "\U0001F4DC Scrolls can enhance your equipment for even stronger boosts!\n"
            "\U0001F4E6 View your inventory at **{pet_url}**\n"
            "\U0001F4AC Stay productive to earn more drops!"
        )).format(drops=drops_block, desc_line=desc_line,
                  pet_url=f"{WEBSITE_URL}/pet/inventory")

        embed.set_footer(text=str(_p(
            'embed:first_drop|footer',
            "Tip: The longer you stay in VC each day, the rarer your drops become!"
        )))

        card_bytes = None
        try:
            card_bytes = render_drop_card(
                item_name=first_drop.get('name', ''),
                rarity=_clean_rarity(first_drop.get('rarity', 'COMMON')),
                category=first_drop.get('category', ''),
                asset_path=first_drop.get('asset_path'),
                description=first_drop.get('description', ''),
                slot=first_drop.get('slot'),
                gold_price=first_drop.get('gold_price'),
                owner_count=first_drop.get('owner_count', 0),
                market_low=first_drop.get('market_low'),
            )
        except Exception:
            logger.debug("Failed to render first drop card for %s", userid)

        if card_bytes:
            embed.set_image(url="attachment://drop_card.gif")

        first_itemid = first_drop.get('itemid', 0)
        view = FirstDropView(self, userid, itemid=first_itemid)

        try:
            user = self.bot.get_user(userid)
            if user is None:
                user = await self.bot.fetch_user(userid)
            if user:
                if card_bytes:
                    card_file = discord.File(BytesIO(card_bytes), filename="drop_card.gif")
                    await user.send(embed=embed, view=view, file=card_file)
                else:
                    await user.send(embed=embed, view=view)
        except discord.Forbidden:
            pass
        except Exception:
            logger.debug(f"Failed to DM first drop to {userid}")
    # --- END AI-REPLACED ---

    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: Drop notification system -- DM + channel with guild drop channel support

    # --- AI-MODIFIED (2026-03-17) ---
    # Purpose: Show bonus breakdown in drop notification footer
    # --- AI-REPLACED (2026-04-07) ---
    # Reason: Richer drop notification with item image, description, and stats
    # What the new code does better: Generates a visual drop card image, shows item
    #   description and equipment slot, and references the item wiki page
    # --- Original code (commented out for rollback) ---
    # def _make_drop_embed(self, drops, bonus_footer=None, vc_tier='', vc_daily_min=0, vc_boost=1.0):
    #     best_rarity = max((_clean_rarity(d.get('rarity','COMMON')) for d in drops), ...)
    #     embed = discord.Embed(title="Item Drop!", color=color)
    #     drop_lines = [f"{r_emoji} **{d['name']}**{cat_label} ({label})" for d in drops]
    #     desc = "\n".join(drop_lines) + "\n" + vc_streak_tip
    #     embed.description = desc
    #     embed.set_footer(text=bonus_footer or "Use /pet ...")
    #     return embed
    # --- End original code ---
    def _make_drop_embed(self, drops: list[dict], bonus_footer: str = None,
                         vc_tier: str = '', vc_daily_min: int = 0,
                         vc_boost: float = 1.0,
                         has_card_image: bool = False) -> discord.Embed:
        """Build an embed for an item drop notification with optional card image."""
        from .gameplay import format_bonus_footer, VC_RARITY_TIERS

        best_rarity = max(
            (_clean_rarity(d.get('rarity', 'COMMON')) for d in drops),
            key=lambda r: list(RARITY_EMBED_COLORS.keys()).index(r) if r in RARITY_EMBED_COLORS else 0
        )
        color = RARITY_EMBED_COLORS.get(best_rarity, 0x9e9e9e)
        embed = discord.Embed(
            title=str(_p('embed:drop|title', "\U0001F381 Item Drop!")),
            color=color
        )

        scroll_drop_lbl = str(_p('embed:first_drop|label_scroll', "[Scroll]"))
        drop_lines = []
        for d in drops:
            rarity = _clean_rarity(d.get('rarity', 'COMMON'))
            r_emoji = RARITY_EMOJI.get(rarity, '\u26AA')
            label = RARITY_LABELS.get(rarity, rarity.title())
            cat = d.get('category', '')
            cat_label = f" [{cat.title()}]" if cat and cat != 'SCROLL' else (
                f" {scroll_drop_lbl}" if cat == 'SCROLL' else "")
            drop_lines.append(f"{r_emoji} **{d['name']}**{cat_label} ({label})")

        desc = "\n".join(drop_lines)

        # Item description (from first drop only, keep it concise)
        if drops:
            item_desc = drops[0].get('description', '')
            if item_desc:
                truncated = item_desc[:120] + ('...' if len(item_desc) > 120 else '')
                desc += f"\n> *{truncated}*"

        desc += "\n"

        if vc_tier:
            hours = vc_daily_min // 60
            mins = vc_daily_min % 60
            time_str = f"{hours}h {mins}m" if hours else f"{mins}m"
            boost_pct = int((vc_boost - 1.0) * 100)
            desc += str(_p(
                'embed:drop|tip:vc_streak',
                "\n\U0001F3AF **Voice Streak**: {tier} ({time_today}) \u2014 +{boost_pct}% rare item chance"
            )).format(
                tier=vc_tier,
                time_today=f"{time_str} today",
                boost_pct=boost_pct,
            )
            next_tier = None
            for threshold, _, name in reversed(VC_RARITY_TIERS):
                if threshold > vc_daily_min:
                    next_tier = (threshold, name)
            if next_tier:
                mins_left = next_tier[0] - vc_daily_min
                desc += str(_p(
                    'embed:drop|tip:vc_unlock',
                    "\n\u23F1\uFE0F {mins_left} more min in VC to reach **{tier_name}**!"
                )).format(mins_left=mins_left, tier_name=next_tier[1])
        elif vc_daily_min > 0:
            next_threshold = 30
            mins_left = next_threshold - vc_daily_min
            desc += str(_p(
                'embed:drop|tip:study_momentum',
                "\n\U0001F4A1 **Tip:** {mins_left} more min in VC today to unlock **Productive Momentum** \u2014 better rarity drops!"
            )).format(mins_left=mins_left)
        else:
            desc += str(_p(
                'embed:drop|tip:vc_daily',
                "\n\U0001F4A1 **Tip:** Spend 30+ min in VC today to unlock rarer item drops!"
            ))

        embed.description = desc

        if has_card_image:
            embed.set_image(url="attachment://drop_card.gif")

        footer_text = bonus_footer or str(_p(
            'embed:drop|footer',
            "Use /pet to view your LionGotchi \u2022 {url}"
        )).format(url=f"{WEBSITE_URL}/pet")
        embed.set_footer(text=footer_text)
        return embed
    # --- END AI-REPLACED ---

    # --- AI-REPLACED (2026-03-20) ---
    # Reason: Rotating hooks for variety, with GIF key for visual teasers
    # What the new code does better: Each teaser highlights a different feature to avoid
    #   repetitive messaging; returns (embed, gif_key) for the caller to attach a preview
    # --- Original code (commented out for rollback) ---
    # def _make_teaser_embed(self):
    #     return Embed(title="LionGotchi", description="Active users earn equipment...")
    # --- End original code ---
    _teaser_counter: int = 0

    def _make_teaser_embed(self) -> tuple[discord.Embed, str]:
        """Build a teaser embed with rotating hooks. Returns (embed, gif_key)."""
        hooks = [
            {
                'title': str(_p('embed:teaser:equipment|title', '\u2728 Earn Gear While You\'re Productive!')),
                'description': str(_p(
                    'embed:teaser:equipment|desc',
                    "**Equipment and scrolls** drop while you're productive!\n\n"
                    "\u2694\uFE0F Equip gear for gold and XP bonuses\n"
                    "\U0001F4DC Enhance equipment with scrolls\n\n"
                    "Use `/pet` to adopt your LionGotchi and start collecting!"
                )),
                'gif_key': 'equipment',
            },
            {
                'title': str(_p('embed:teaser:farm|title', '\U0001F331 Grow Your Own Farm!')),
                'description': str(_p(
                    'embed:teaser:farm|desc',
                    "LionGotchi pets come with a **15-plot farm**!\n\n"
                    "\U0001FAB4 Plant seeds \u2022 \U0001F4A7 Water daily \u2022 "
                    "\U0001F33E Harvest for gold\n"
                    "Your farm grows automatically as you're productive.\n\n"
                    "Use `/pet` to get started!"
                )),
                'gif_key': 'farm',
            },
            {
                'title': str(_p('embed:teaser:pet|title', '\U0001F3E0 Your Pet Is Waiting!')),
                'description': str(_p(
                    'embed:teaser:pet|desc',
                    "Adopt a **LionGotchi** \u2014 a virtual pet that grows "
                    "alongside your productive sessions!\n\n"
                    "\U0001F43E Care for it \u2022 \u2694\uFE0F Gear it up \u2022 "
                    "\U0001F4B0 Trade with friends\n\n"
                    "Use `/pet` to adopt yours!"
                )),
                'gif_key': 'welcome',
            },
        ]
        hook = hooks[self._teaser_counter % len(hooks)]
        self._teaser_counter += 1
        embed = discord.Embed(
            title=hook['title'],
            description=hook['description'],
            color=0xffd700,
        )
        embed.set_footer(text=str(_p(
            'embed:first_encounter|footer',
            "The more productive you are, the more you earn \u2022 {url}"
        )).format(url=f"{WEBSITE_URL}/pet"))
        return embed, hook['gif_key']
    # --- END AI-REPLACED ---

    # --- AI-REPLACED (2026-03-20) ---
    # Reason: Use centralized _get_guild_lg_config instead of standalone query
    # What the new code does better: Shares cache with other LG config reads
    # --- Original code (commented out for rollback) ---
    # async def _get_guild_drop_channel(self, guildid: int):
    #     try:
    #         rows = await _db_fetch(self.bot,
    #             "SELECT lg_drop_channel FROM guild_config WHERE guildid = %s",
    #             guildid
    #         )
    #         if rows and rows[0].get('lg_drop_channel'):
    #             ch = self.bot.get_channel(rows[0]['lg_drop_channel'])
    #             if ch:
    #                 return ch
    #     except Exception:
    #         pass
    #     return None
    # --- End original code ---
    async def _get_guild_drop_channel(self, guildid: int):
        """Return the guild's configured LG drop channel, or None."""
        lg_conf = await self._get_guild_lg_config(guildid)
        chid = lg_conf.get('lg_drop_channel')
        if chid:
            ch = self.bot.get_channel(chid)
            if ch:
                return ch
        return None
    # --- END AI-REPLACED ---

    # --- AI-MODIFIED (2026-03-17) ---
    # Purpose: Compute bonus footer for drop notifications showing active bonuses
    # --- AI-MODIFIED (2026-03-22) ---
    # Purpose: Accept VC Study Streak info and pass to drop embed
    async def _send_drop_notification(self, userid: int, drops: list[dict],
                                       guildid: int = None, active_channel=None,
                                       vc_tier: str = '', vc_daily_min: int = 0,
                                       vc_boost: float = 1.0):
        """Send drop notifications respecting user preference and guild drop channel."""
        from .gameplay import calc_all_bonuses, format_bonus_footer

        now = datetime.now(timezone.utc)
        last = self._drop_notif_cooldowns.get(userid)
        if last and (now - last).total_seconds() < NOTIF_COOLDOWN_SECONDS:
            return
        self._drop_notif_cooldowns[userid] = now

        pref = 'ALL'
        try:
            rows = await _db_fetch(self.bot,
                "SELECT drop_notif FROM lg_pets WHERE userid = %s", userid)
            if rows:
                raw_pref = rows[0].get('drop_notif') or 'ALL'
                pref = raw_pref.value if hasattr(raw_pref, 'value') else raw_pref
        except Exception:
            pass
        if pref == 'MUTED':
            return

        user_tier, server_premium = await self._get_premium_context(userid, guildid)
        bonuses = await calc_all_bonuses(self.bot, userid,
                                          user_tier=user_tier, server_premium=server_premium)
        bonus_footer = format_bonus_footer(bonuses)

        # --- AI-MODIFIED (2026-04-07) ---
        # Purpose: Generate drop card image and attach it to the notification
        from .item_renderer import render_drop_card

        card_bytes = None
        first_drop = drops[0] if drops else {}
        try:
            card_bytes = render_drop_card(
                item_name=first_drop.get('name', ''),
                rarity=_clean_rarity(first_drop.get('rarity', 'COMMON')),
                category=first_drop.get('category', ''),
                asset_path=first_drop.get('asset_path'),
                description=first_drop.get('description', ''),
                slot=first_drop.get('slot'),
                gold_price=first_drop.get('gold_price'),
                owner_count=first_drop.get('owner_count', 0),
                market_low=first_drop.get('market_low'),
            )
        except Exception:
            logger.debug("Failed to render drop card for %s", userid)

        embed = self._make_drop_embed(drops, bonus_footer=bonus_footer,
                                       vc_tier=vc_tier, vc_daily_min=vc_daily_min,
                                       vc_boost=vc_boost,
                                       has_card_image=card_bytes is not None)
        # --- END AI-MODIFIED ---

        daily_progress = self._format_daily_progress(userid)
        embed.description += f"\n{daily_progress}"

        send_dm = pref in ('ALL', 'DM_ONLY')
        send_channel = pref == 'ALL'

        # --- AI-MODIFIED (2026-04-07) ---
        # Purpose: Pass itemid to views and attach card image to messages
        first_itemid = first_drop.get('itemid', 0)

        if send_dm:
            try:
                user = self.bot.get_user(userid)
                if user is None:
                    user = await self.bot.fetch_user(userid)
                if user:
                    view = DropNotificationView(self, userid, itemid=first_itemid)
                    if card_bytes:
                        card_file = discord.File(BytesIO(card_bytes), filename="drop_card.gif")
                        await user.send(embed=embed, view=view, file=card_file)
                    else:
                        await user.send(embed=embed, view=view)
            except discord.Forbidden:
                pass
            except Exception:
                logger.debug(f"Failed to DM drop notification to {userid}")

        if send_channel and guildid:
            try:
                lg_conf = await self._get_guild_lg_config(guildid)
                custom_delete = lg_conf.get('lg_drop_delete_after')
                target_ch = await self._get_guild_drop_channel(guildid)
                if target_ch:
                    if card_bytes:
                        card_file = discord.File(BytesIO(card_bytes), filename="drop_card.gif")
                        await target_ch.send(
                            content=f"<@{userid}>",
                            embed=embed,
                            file=card_file,
                            delete_after=custom_delete
                        )
                    else:
                        await target_ch.send(
                            content=f"<@{userid}>",
                            embed=embed,
                            delete_after=custom_delete
                        )
            except discord.Forbidden:
                pass
            except Exception:
                logger.debug(f"Failed to send channel drop notification for {userid}")
        # --- END AI-MODIFIED ---

    # --- AI-REPLACED (2026-03-20) ---
    # Reason: Visual teasers with GIF previews and interactive Adopt button
    # What the new code does better: Attaches a showcase GIF, uses rotating hooks,
    #   includes an interactive Adopt button that opens the onboarding tutorial
    # --- Original code (commented out for rollback) ---
    # async def _send_teaser(self, userid, guildid=None, active_channel=None):
    #     embed = self._make_teaser_embed()
    #     view = TeaserView()
    #     user.send(embed=embed, view=view)
    #     ch.send(content=f"<@{userid}>", embed=embed, view=TeaserView(), delete_after=60)
    # --- End original code ---
    async def _send_teaser(self, userid: int, guildid: int = None, active_channel=None):
        """Send a visual teaser notification with GIF preview and Adopt button."""
        embed, gif_key = self._make_teaser_embed()
        view = TeaserView(cog=self, user_id=userid)

        gif_file = None
        try:
            gif_bytes = await self._onboarding_gifs.get(gif_key)
            gif_file = discord.File(BytesIO(gif_bytes), filename=f"{gif_key}.gif")
            embed.set_image(url=f"attachment://{gif_key}.gif")
        except Exception:
            logger.debug(f"Failed to load teaser GIF: {gif_key}")

        if guildid and active_channel:
            try:
                target_ch = await self._get_guild_drop_channel(guildid)
                lg_conf = await self._get_guild_lg_config(guildid)
                custom_delete = lg_conf.get('lg_drop_delete_after')
                ch = target_ch or active_channel
                if target_ch:
                    del_after = custom_delete
                else:
                    del_after = custom_delete if custom_delete else 120
                kwargs = {
                    'content': f"<@{userid}>",
                    'embed': embed,
                    'view': TeaserView(cog=self, user_id=userid),
                    'delete_after': del_after,
                }
                if gif_file:
                    kwargs['file'] = gif_file
                await ch.send(**kwargs)
            except Exception:
                pass
    # --- END AI-REPLACED ---

    # --- AI-MODIFIED (2026-03-17) ---
    # Purpose: Level-up notification with bonus breakdown
    async def _send_level_up_notification(self, userid: int, new_level: int, levels_gained: int,
                                           gold_earned: int, xp_earned: int,
                                           guildid: int = None, active_channel=None):
        """Send a level-up notification via DM and/or guild drop channel."""
        from .gameplay import LEVEL_UP_GOLD_BONUS, calc_all_bonuses, format_bonus_summary

        pref = 'ALL'
        try:
            rows = await _db_fetch(self.bot,
                "SELECT drop_notif FROM lg_pets WHERE userid = %s", userid)
            if rows:
                raw_pref = rows[0].get('drop_notif') or 'ALL'
                pref = raw_pref.value if hasattr(raw_pref, 'value') else raw_pref
        except Exception:
            pass
        if pref == 'MUTED':
            return

        level_gold = levels_gained * LEVEL_UP_GOLD_BONUS

        user_tier, server_premium = await self._get_premium_context(userid, guildid)
        bonuses = await calc_all_bonuses(self.bot, userid,
                                          user_tier=user_tier, server_premium=server_premium)
        bonus_text = format_bonus_summary(bonuses)

        e_xp = _lg_emoji('lg_xp', '\u2B50')
        e_coin = _lg_emoji('lg_coin', '\U0001F4B0')

        # --- AI-MODIFIED (2026-03-20) ---
        # Purpose: Show daily gold/XP cap progress in level-up notification
        daily_progress = self._format_daily_progress(userid)
        desc = str(_p(
            'embed:levelup|desc',
            "{e_xp} Your LionGotchi reached **Level {new_level}**!\n\n"
            "{e_coin} **+{level_gold}G** level-up bonus\n"
            "Session: **+{gold_earned}G** gold, **+{xp_earned}** XP\n"
            "{daily_progress}"
        )).format(
            e_xp=e_xp, new_level=new_level, e_coin=e_coin, level_gold=level_gold,
            gold_earned=gold_earned, xp_earned=xp_earned, daily_progress=daily_progress,
        )
        if bonus_text:
            desc += str(_p(
                'embed:pet_card|active_bonuses_block',
                "\n\n\u2500\u2500\u2500 **Active Bonuses** \u2500\u2500\u2500\n{bonus}"
            )).format(bonus=bonus_text)

        embed = discord.Embed(
            title=str(_p('embed:levelup|title', "\U0001F31F Level Up!")),
            description=desc,
            color=0xFFD700
        )
        embed.set_footer(text=str(_p(
            'embed:drop|footer',
            "Use /pet to view your LionGotchi \u2022 {url}"
        )).format(url=f"{WEBSITE_URL}/pet"))
        # --- END AI-MODIFIED ---

        send_dm = pref in ('ALL', 'DM_ONLY')
        # --- AI-REPLACED (2026-03-22) ---
        # Reason: Channel notifications were fully disabled (spam complaints).
        # What the new code does better: Re-enables channel sends ONLY when the admin
        #   has explicitly configured a drop channel (no fallback to active_channel).
        # --- Original code (commented out for rollback) ---
        # send_channel = False  # disabled 2026-03-21
        # --- End original code ---
        send_channel = pref == 'ALL'
        # --- END AI-REPLACED ---

        if send_dm:
            try:
                user = self.bot.get_user(userid)
                if user is None:
                    user = await self.bot.fetch_user(userid)
                if user:
                    view = LevelUpNotificationView(self, userid)
                    await user.send(embed=embed, view=view)
            except discord.Forbidden:
                pass
            except Exception:
                logger.debug(f"Failed to DM level-up notification to {userid}")

        if send_channel and guildid:
            try:
                lg_conf = await self._get_guild_lg_config(guildid)
                custom_delete = lg_conf.get('lg_drop_delete_after')
                target_ch = await self._get_guild_drop_channel(guildid)
                # --- AI-MODIFIED (2026-03-22) ---
                # Purpose: Only send to explicitly configured drop channel, NOT to
                # random active channels (that was the original spam complaint)
                if target_ch:
                    await target_ch.send(
                        content=f"<@{userid}>", embed=embed,
                        delete_after=custom_delete
                    )
                # --- END AI-MODIFIED ---
            except discord.Forbidden:
                pass
            except Exception:
                logger.debug(f"Failed to send channel level-up notification for {userid}")
    # --- END AI-MODIFIED ---

    # --- AI-REPLACED (2026-03-19) ---
    # Reason: Stat redesign -- apply decay and pass mood to process_voice_activity
    # What the new code does better: Mood multiplier affects gold/XP, pet warning notifications
    # --- Original code (commented out for rollback) ---
    # @LionCog.listener('on_voice_session_end')
    # async def on_voice_end(self, session_data, end_time):
    #     result = await process_voice_activity(self.bot, userid, duration, ...)
    # --- End original code ---
    @LionCog.listener('on_voice_session_end')
    async def on_voice_end(self, session_data, end_time):
        try:
            userid = session_data.userid
            start = session_data.start_time
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            duration = int((end_time - start).total_seconds())
            if duration < 60:
                return

            guildid = session_data.guildid
            channelid = getattr(session_data, 'channelid', None)
            active_channel = self.bot.get_channel(channelid) if channelid else None

            # --- AI-MODIFIED (2026-03-20) ---
            # Purpose: Check lg_enabled and lg_activity_role before processing voice activity
            lg_conf = await self._get_guild_lg_config(guildid)
            if not lg_conf.get('lg_enabled', True):
                return

            activity_role_id = lg_conf.get('lg_activity_role')
            if activity_role_id:
                guild = self.bot.get_guild(guildid)
                if guild:
                    member = guild.get_member(userid)
                    if member and member.get_role(activity_role_id) is None:
                        return
            # --- END AI-MODIFIED ---

            pet = await self.data.Pet.fetch(userid)
            if pet is None:
                # --- AI-MODIFIED (2026-03-20) ---
                # Purpose: Respect lg_teaser_enabled guild setting
                if random.random() < TEASER_CHANCE and lg_conf.get('lg_teaser_enabled', True):
                    await self._send_teaser(userid, guildid, active_channel)
                # --- END AI-MODIFIED ---
                return

            pet = await self._apply_decay(pet)
            mood = calc_mood(pet.food, pet.bath, pet.sleep)

            user_tier, server_premium = await self._get_premium_context(userid, guildid)
            # --- AI-MODIFIED (2026-03-20) ---
            # Purpose: Reset daily caps BEFORE computing remaining amounts,
            # otherwise first session after UTC midnight uses yesterday's stale caps
            self._check_daily_reset()
            # --- AI-MODIFIED (2026-03-22) ---
            # Purpose: Track daily voice minutes for VC Study Streak rarity boost
            voice_minutes = duration / 60.0
            self._record_voice_minutes(userid, voice_minutes)
            vc_boost, vc_tier, vc_daily_min = self._get_vc_rarity_boost(userid)
            # --- END AI-MODIFIED ---
            gold_remaining = max(0, DAILY_GOLD_CAP - self._daily_gold_earned.get(userid, 0))
            xp_remaining = max(0, DAILY_XP_CAP - self._daily_xp_earned.get(userid, 0))
            can_drop = self._can_drop(userid)
            # --- END AI-MODIFIED ---
            result = await process_voice_activity(self.bot, userid, duration,
                                                   user_tier=user_tier, server_premium=server_premium,
                                                   max_gold=gold_remaining, max_xp=xp_remaining,
                                                   allow_drop=can_drop, mood=mood,
                                                   vc_quality_boost=vc_boost)
            earned_gold = result.get('gold_earned', 0) if result else 0
            earned_xp = result.get('xp_earned', 0) if result else 0
            if earned_gold > 0:
                self._daily_gold_earned[userid] = self._daily_gold_earned.get(userid, 0) + earned_gold
            if earned_xp > 0:
                self._daily_xp_earned[userid] = self._daily_xp_earned.get(userid, 0) + earned_xp

            # --- AI-MODIFIED (2026-03-24) ---
            # Purpose: Award family XP proportional to pet XP earned (with all bonuses applied)
            if earned_xp > 0:
                await award_family_xp(self.bot, userid, earned_xp)
            # --- END AI-MODIFIED ---

            drops = result.get('drops') if result else None
            if drops:
                self._record_drop(userid)
                await self._send_drop_notification(userid, drops, guildid, active_channel,
                                                    vc_tier=vc_tier, vc_daily_min=vc_daily_min,
                                                    vc_boost=vc_boost)

            levels = result.get('levels', 0) if result else 0
            if levels > 0:
                await self._send_level_up_notification(
                    userid, result.get('new_level') or 0, levels,
                    result.get('gold_earned', 0), result.get('xp_earned', 0),
                    guildid, active_channel
                )

            await self._check_pet_warning(userid, pet)
        except Exception:
            logger.exception("Error in LionGotchi voice_session_end handler")
    # --- END AI-REPLACED ---

    # --- AI-REPLACED (2026-03-19) ---
    # Reason: Stat redesign -- apply decay and pass mood to process_text_activity
    # What the new code does better: Mood multiplier affects gold/XP, pet warning notifications
    # --- Original code (commented out for rollback) ---
    # @LionCog.listener('on_text_session_complete')
    # async def on_text_complete(self, guildid, userid, message_count, xp_earned):
    #     result = await process_text_activity(self.bot, userid, capped_count, ...)
    # --- End original code ---
    @LionCog.listener('on_text_session_complete')
    async def on_text_complete(self, guildid, userid, message_count, xp_earned):
        try:
            if message_count < 5:
                return

            pet = await self.data.Pet.fetch(userid)
            if pet is None:
                return

            pet = await self._apply_decay(pet)
            mood = calc_mood(pet.food, pet.bath, pet.sleep)

            user_tier, server_premium = await self._get_premium_context(userid, guildid)
            capped_count = min(message_count, LG_TEXT_SESSION_MSG_CAP)
            # --- AI-MODIFIED (2026-03-20) ---
            # Purpose: Reset daily caps BEFORE computing remaining amounts,
            # otherwise first session after UTC midnight uses yesterday's stale caps
            self._check_daily_reset()
            gold_remaining = max(0, DAILY_GOLD_CAP - self._daily_gold_earned.get(userid, 0))
            xp_remaining = max(0, DAILY_XP_CAP - self._daily_xp_earned.get(userid, 0))
            # --- END AI-MODIFIED ---
            result = await process_text_activity(
                self.bot, userid, capped_count,
                user_tier=user_tier, server_premium=server_premium,
                skip_drop=True,
                max_gold=gold_remaining, max_xp=xp_remaining,
                mood=mood
            )
            earned_gold = result.get('gold_earned', 0) if result else 0
            earned_xp = result.get('xp_earned', 0) if result else 0
            if earned_gold > 0:
                self._daily_gold_earned[userid] = self._daily_gold_earned.get(userid, 0) + earned_gold
            if earned_xp > 0:
                self._daily_xp_earned[userid] = self._daily_xp_earned.get(userid, 0) + earned_xp

            # --- AI-MODIFIED (2026-03-24) ---
            # Purpose: Award family XP proportional to pet XP earned (with all bonuses applied)
            if earned_xp > 0:
                await award_family_xp(self.bot, userid, earned_xp)
            # --- END AI-MODIFIED ---

            levels = result.get('levels', 0) if result else 0
            if levels > 0:
                await self._send_level_up_notification(
                    userid, result.get('new_level') or 0, levels,
                    result.get('gold_earned', 0), result.get('xp_earned', 0),
                    guildid
                )

            await self._check_pet_warning(userid, pet)
        except Exception:
            logger.exception("Error in LionGotchi text_session_complete handler")
    # --- END AI-REPLACED ---

    # --- AI-REPLACED (2026-04-01) ---
    # Reason: Pet warning DMs were too frequent (every 4h, in-memory cooldown reset on restart)
    # What the new code does better: Cooldown is now 7 days and persisted in the DB
    #   (last_pet_warning column) so it survives restarts and works across all 32 shards
    # --- Original code (commented out for rollback) ---
    # async def _check_pet_warning(self, userid: int, pet):
    #     """Send a DM warning if any pet need is at 2 or below, rate-limited."""
    #     try:
    #         if pet.food > 2 and pet.bath > 2 and pet.sleep > 2:
    #             return
    #         now = datetime.now(timezone.utc)
    #         last_warning = self._pet_warning_cooldowns.get(userid)
    #         if last_warning and (now - last_warning).total_seconds() < PET_WARNING_COOLDOWN_SECONDS:
    #             return
    #         notif_pref = getattr(pet, 'drop_notif', 'ALL')
    #         if hasattr(notif_pref, 'value'):
    #             notif_pref = notif_pref.value
    #         if notif_pref == 'MUTED':
    #             return
    #         low_needs = []
    #         if pet.food <= 2:
    #             low_needs.append("\U0001F356 Hunger")
    #         if pet.bath <= 2:
    #             low_needs.append("\U0001F9FC Cleanliness")
    #         if pet.sleep <= 2:
    #             low_needs.append("\U0001F4A4 Energy")
    #         pet_name = pet.pet_name or "Leo"
    #         mood = calc_mood(pet.food, pet.bath, pet.sleep)
    #         mood_label = MOOD_LABELS.get(mood, 'Okay')
    #         mood_mult = MOOD_MULTIPLIERS.get(mood, 1.0)
    #         needs_text = ", ".join(low_needs)
    #         embed = discord.Embed(
    #             title=f"\U0001F43E {pet_name} needs attention!",
    #             color=0xf0c040 if mood >= 3 else 0xe04040,
    #             description=(
    #                 f"**Low:** {needs_text}\n\n"
    #                 f"Mood: **{mood_label}** ({mood_mult:.2f}x Gold & XP)\n\n"
    #                 f"Start a study session or feed them before they get sad!"
    #             ),
    #         )
    #         embed.set_footer(text=f"Use /pet to care for your LionGotchi \u2022 {WEBSITE_URL}/pet")
    #         view = LevelUpNotificationView(self, userid)
    #         user = self.bot.get_user(userid)
    #         if user is None:
    #             user = await self.bot.fetch_user(userid)
    #         if user:
    #             await user.send(embed=embed, view=view)
    #             self._pet_warning_cooldowns[userid] = now
    #     except discord.Forbidden:
    #         pass
    #     except Exception:
    #         logger.debug(f"Failed to send pet warning to {userid}", exc_info=True)
    # --- End original code ---
    async def _check_pet_warning(self, userid: int, pet):
        """Send a DM warning if any pet need is at 2 or below, rate-limited to once per week via DB."""
        try:
            if pet.food > 2 and pet.bath > 2 and pet.sleep > 2:
                return

            now = datetime.now(timezone.utc)

            last_warning = getattr(pet, 'last_pet_warning', None)
            if last_warning and (now - last_warning).total_seconds() < PET_WARNING_COOLDOWN_SECONDS:
                return

            notif_pref = getattr(pet, 'drop_notif', 'ALL')
            if hasattr(notif_pref, 'value'):
                notif_pref = notif_pref.value
            if notif_pref == 'MUTED':
                return

            low_needs = []
            if pet.food <= 2:
                low_needs.append(str(_p('embed:pet_warning|need_hunger', "\U0001F356 Hunger")))
            if pet.bath <= 2:
                low_needs.append(str(_p('embed:pet_warning|need_clean', "\U0001F9FC Cleanliness")))
            if pet.sleep <= 2:
                low_needs.append(str(_p('embed:pet_warning|need_energy', "\U0001F4A4 Energy")))

            pet_name = pet.pet_name or "Leo"
            mood = calc_mood(pet.food, pet.bath, pet.sleep)
            mood_label = MOOD_LABELS.get(mood, 'Okay')
            mood_mult = MOOD_MULTIPLIERS.get(mood, 1.0)

            needs_text = ", ".join(low_needs)
            embed = discord.Embed(
                title=str(_p(
                    'embed:pet_warning|title',
                    "\U0001F43E {pet_name} needs attention!"
                )).format(pet_name=pet_name),
                color=0xf0c040 if mood >= 3 else 0xe04040,
                description=str(_p(
                    'embed:pet_warning|desc',
                    "**Low:** {needs}\n\n"
                    "Mood: **{mood_label}** ({mood_mult:.2f}x Gold & XP)\n\n"
                    "Start a session or feed them before they get sad!"
                )).format(
                    needs=needs_text, mood_label=mood_label, mood_mult=mood_mult,
                ),
            )
            embed.set_footer(text=str(_p(
                'embed:pet_warning|footer',
                "Use /pet to care for your LionGotchi \u2022 {url}"
            )).format(url=f"{WEBSITE_URL}/pet"))

            view = LevelUpNotificationView(self, userid)

            user = self.bot.get_user(userid)
            if user is None:
                user = await self.bot.fetch_user(userid)
            if user:
                await user.send(embed=embed, view=view)
                async with self.bot.db.connection() as conn:
                    await conn.execute(
                        "UPDATE lg_pets SET last_pet_warning = %s WHERE userid = %s",
                        [now, userid]
                    )
                if pet.data is not None:
                    pet.data['last_pet_warning'] = now
        except discord.Forbidden:
            pass
        except Exception:
            logger.debug(f"Failed to send pet warning to {userid}", exc_info=True)
    # --- END AI-REPLACED ---

    # ---- Slash commands ----

    @cmds.hybrid_command(
        name="pet",
        description="View your LionGotchi pet!"
    )
    async def pet_cmd(self, ctx: LionContext):
        await self._show_pet(ctx.interaction)

    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: Admin command to set/clear the guild's LionGotchi drop notification channel

    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Fix misleading "leave empty to clear" text -- Discord slash commands
    # don't allow submitting an empty channel field. Changed to instruct users to
    # omit the option entirely to clear.
    @cmds.hybrid_command(
        name="petdrops",
        description="(Admin) Set or clear the LionGotchi drop notification channel"
    )
    @appcmds.describe(channel="Channel for drop notifications (omit this option to clear)")
    # --- END AI-MODIFIED ---
    @cmds.has_permissions(administrator=True)
    async def petdrops_cmd(self, ctx: LionContext,
                           channel: discord.TextChannel = None):
        if not ctx.guild:
            await ctx.reply("This command can only be used in a server.", ephemeral=True)
            return
        guildid = ctx.guild.id
        if channel:
            await _db_exec(self.bot,
                "UPDATE guild_config SET lg_drop_channel = %s WHERE guildid = %s",
                channel.id, guildid
            )
            # --- AI-MODIFIED (2026-03-20) ---
            # Purpose: Invalidate LG config cache when drop channel changes via command
            self._guild_lg_cache.pop(guildid, None)
            # --- END AI-MODIFIED ---
            await ctx.reply(
                f"\U0001F43E LionGotchi drop notifications will be sent to {channel.mention}.",
                ephemeral=True
            )
        else:
            await _db_exec(self.bot,
                "UPDATE guild_config SET lg_drop_channel = NULL WHERE guildid = %s",
                guildid
            )
            # --- AI-MODIFIED (2026-03-20) ---
            # Purpose: Invalidate LG config cache when drop channel changes via command
            self._guild_lg_cache.pop(guildid, None)
            # --- END AI-MODIFIED ---
            await ctx.reply(
                "\U0001F43E LionGotchi drop notifications channel cleared. "
                "Drops will appear in the user's active channel.",
                ephemeral=True
            )

    # --- AI-MODIFIED (2026-03-20) ---
    # Purpose: Launch announcement command for server admins to post a rich
    #          LionGotchi introduction embed with GIF preview to any channel
    @cmds.hybrid_command(
        name="liongotchi-announce",
        description="(Admin) Post a LionGotchi introduction announcement to a channel"
    )
    @appcmds.describe(channel="Channel to post the announcement in")
    @cmds.has_permissions(administrator=True)
    async def liongotchi_announce_cmd(self, ctx: LionContext,
                                      channel: discord.TextChannel = None):
        if not ctx.guild:
            await ctx.reply("This command can only be used in a server.", ephemeral=True)
            return

        target = channel or ctx.channel

        pet_count = getattr(self, '_cached_pet_count', 0)
        social_line = ""
        if pet_count and pet_count > 100:
            social_line = f"\n\U0001F465 **{pet_count:,} members** have already adopted their LionGotchi!\n"

        embed = discord.Embed(
            title="\U0001F981 LionGotchi Has Arrived!",
            color=0xffd700,
            description=(
                "**LionGotchi** is a virtual pet system built into LionBot!\n"
                "Your pet grows alongside your productive sessions.\n"
                f"{social_line}\n"
                "\U0001F43E **Adopt a pet** \u2014 name it, care for it, watch it level up\n"
                "\u2694\uFE0F **Earn equipment** \u2014 gear drops while you're productive\n"
                "\U0001F331 **Grow a farm** \u2014 plant seeds, water daily, harvest for gold\n"
                "\U0001F3E0 **Customize a room** \u2014 furniture, themes, and trophies\n"
                "\U0001F4B0 **Trade on the marketplace** \u2014 buy and sell with other users\n"
                "\U0001F4DC **Enhance gear** \u2014 use scrolls to boost equipment stats\n\n"
                "Type **`/pet`** to get started! It's free for everyone."
            )
        )
        embed.set_footer(text=f"The more productive you are, the more you earn \u2022 {WEBSITE_URL}/pet")

        gif_file = None
        try:
            gif_bytes = await self._onboarding_gifs.get('welcome')
            gif_file = discord.File(BytesIO(gif_bytes), filename="liongotchi.gif")
            embed.set_image(url="attachment://liongotchi.gif")
        except Exception:
            logger.debug("Failed to load GIF for announcement")

        kwargs = {'embed': embed}
        if gif_file:
            kwargs['file'] = gif_file

        try:
            await target.send(**kwargs)
            await ctx.reply(
                f"\U0001F43E LionGotchi announcement posted to {target.mention}!",
                ephemeral=True
            )
        except discord.Forbidden:
            await ctx.reply(
                f"I don't have permission to send messages in {target.mention}.",
                ephemeral=True
            )
        except Exception:
            await ctx.reply("Failed to send announcement. Check my permissions.", ephemeral=True)
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-04-10) ---
    # Purpose: One-time adoption nudge -- fires after a successful slash command for users
    #          without a pet, sends a DM (fallback to drop channel), then never again.
    #          7 anti-spam layers: feature-launch gate, hourly cap, DB flag, in-memory skip set,
    #          guild gate, command exclusion, per-send cooldown.
    @LionCog.listener('on_app_command_completion')
    async def _on_command_for_nudge(self, interaction: discord.Interaction, command):
        try:
            userid = interaction.user.id

            if userid in self._nudge_skip_users:
                return

            cmd_name = getattr(command, 'name', '') or ''
            if cmd_name in _NUDGE_EXCLUDED_COMMANDS:
                return

            if datetime.now(timezone.utc) < _NUDGE_FEATURE_LAUNCH_TS:
                return

            if not interaction.guild:
                return
            guildid = interaction.guild.id

            lg_conf = await self._get_guild_lg_config(guildid)
            if not lg_conf.get('lg_enabled', True):
                return
            if not lg_conf.get('lg_teaser_enabled', True):
                return

            pet = await self.data.Pet.fetch(userid)
            if pet is not None:
                self._nudge_skip_users.add(userid)
                return

            rows = await _db_fetch(self.bot,
                "SELECT lg_nudge_sent_at FROM user_config WHERE userid = %s", userid)
            if rows and rows[0].get('lg_nudge_sent_at') is not None:
                self._nudge_skip_users.add(userid)
                return

            now = _time.monotonic()
            self._nudge_send_times = [t for t in self._nudge_send_times if now - t < 3600]
            if len(self._nudge_send_times) >= NUDGE_HOURLY_CAP_PER_SHARD:
                return

            if now - self._last_nudge_sent < NUDGE_COOLDOWN_SECONDS:
                return

            await self._send_adoption_nudge(userid, guildid)
        except Exception:
            logger.debug("Error in adoption nudge check", exc_info=True)

    async def _send_adoption_nudge(self, userid: int, guildid: int):
        """Send a one-time DM encouraging the user to adopt a pet. Falls back to drop channel."""
        now_mono = _time.monotonic()
        self._last_nudge_sent = now_mono
        self._nudge_send_times.append(now_mono)

        pet_count = getattr(self, '_cached_pet_count', 0) or 0
        item_count = self._cached_item_drop_count
        farm_count = self._cached_farm_count

        stats_lines = []
        if pet_count > 50:
            stats_lines.append(f"\U0001F43E **{pet_count:,}** members have adopted a LionGotchi")
        if item_count > 50:
            stats_lines.append(f"\U0001F392 **{item_count:,}** items dropped to active members")
        if farm_count > 10:
            stats_lines.append(f"\U0001F331 **{farm_count:,}** farms growing right now")
        stats_block = "\n".join(stats_lines) + "\n\n" if stats_lines else ""

        embed = discord.Embed(
            title="\U0001F981 Your Sessions Could Be More Fun!",
            color=0xffd700,
            description=(
                f"Did you know LionBot has a **virtual pet system**?\n\n"
                f"{stats_block}"
                f"\U0001F4B0 Earn **Gold** by being productive in voice channels and chatting\n"
                f"\u2694\uFE0F Collect **equipment and scrolls** that drop while you're productive\n"
                f"\U0001F33E **Grow a farm** and harvest crops for profit\n"
                f"\U0001F4CA **Trade on the marketplace** with other users\n\n"
                f"Use `/pet` to adopt yours for free \u2014 it takes 10 seconds!"
            ),
        )
        embed.set_footer(
            text=f"The more productive you are, the more you earn \u2022 {WEBSITE_URL}/pet/tutorial"
        )

        view = AdoptionNudgeView()

        sent = False
        try:
            user = self.bot.get_user(userid)
            if user is None:
                user = await self.bot.fetch_user(userid)
            if user:
                await user.send(embed=embed, view=view)
                sent = True
        except discord.Forbidden:
            pass
        except Exception:
            logger.debug(f"Failed to DM adoption nudge to {userid}", exc_info=True)

        if not sent:
            try:
                drop_ch = await self._get_guild_drop_channel(guildid)
                if drop_ch:
                    lg_conf = await self._get_guild_lg_config(guildid)
                    custom_delete = lg_conf.get('lg_drop_delete_after')
                    del_after = custom_delete if custom_delete else 120
                    await drop_ch.send(
                        content=f"<@{userid}>",
                        embed=embed,
                        view=AdoptionNudgeView(),
                        delete_after=del_after,
                    )
            except Exception:
                logger.debug(f"Failed to send adoption nudge to drop channel for {userid}")

        try:
            await _db_exec(self.bot,
                "UPDATE user_config SET lg_nudge_sent_at = NOW() WHERE userid = %s", userid)
        except Exception:
            logger.debug(f"Failed to mark nudge as sent for {userid}")
        self._nudge_skip_users.add(userid)
    # --- END AI-MODIFIED ---

    # --- END AI-MODIFIED ---
