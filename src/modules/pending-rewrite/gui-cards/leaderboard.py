import asyncio
from io import BytesIO
from PIL import Image, ImageDraw

from ..base import Card, Layout, fielded, Skin, FieldDesc
from ..base.Avatars import avatar_manager
from ..base.Skin import (
    AssetField, RGBAAssetField, AssetPathField, BlobField, StringField, NumberField,
    FontField, ColourField, ComputedField
)


class LeaderboardEntry:
    __slots__ = (
        'userid',
        'position',
        'time',
        'name',
        'avatar_key',
        'image'
    )

    def __init__(self, userid, position, time, name, avatar_key):
        self.userid = userid

        self.position = position
        self.time = time

        self.name = name
        self.name = ''.join(i if ord(i) < 128 or i == '∞' else '*' for i in self.name)

        self.avatar_key = avatar_key

        self.image = None

    async def get_avatar(self):
        if not self.image:
            self.image = await avatar_manager().get_avatar(
                *self.avatar_key,
                size=512 if self.position in (1, 2, 3) else 256
            )

    def convert_avatar(self):
        if self.image:
            with BytesIO(self.image) as data:
                self.image = Image.open(data).convert('RGBA')


@fielded
class LeaderboardSkin(Skin):
    _env = {
        'scale': 2  # General size scale to match background resolution
    }

    header_text_pre_gap: NumberField = 20
    header_text: StringField = "STUDY TIME LEADERBOARD"
    header_text_font: FontField = ('ExtraBold', 80)
    header_text_size: ComputedField = lambda skin: skin.header_text_font.getsize(skin.header_text)
    header_text_colour: ColourField = '#DDB21D'

    header_text_gap: NumberField = 15
    header_text_line_width: NumberField = 0
    header_text_line_gap: NumberField = 20

    subheader_name_font: FontField = ('SemiBold', 27)
    subheader_name_colour: ColourField = '#FFFFFF'
    subheader_value_font: FontField = ('Regular', 27)
    subheader_value_colour: ColourField = '#FFFFFF'

    header_gap: NumberField = 20

    # First page constants
    first_bg_path: AssetPathField = "leaderboard/first_page_background.png"
    header_bg_gap: NumberField = 20
    first_header_height: NumberField = 694

    first_avatar_mask: RGBAAssetField = "leaderboard/medal_avatar_mask.png"

    first_avatar_bg: RGBAAssetField = "leaderboard/first_avatar_background.png"
    second_avatar_bg: RGBAAssetField = "leaderboard/second_avatar_background.png"
    third_avatar_bg: RGBAAssetField = "leaderboard/third_avatar_background.png"

    first_avatar_gap: NumberField = 20

    first_top_gap: NumberField = 20

    top_position_font: FontField = ('Bold', 30)
    top_position_colour: ColourField = '#FFFFFF'
    top_name_font: FontField = ('Bold', 30)
    top_name_colour: ColourField = '#DDB21D'
    top_hours_font: FontField = ('Medium', 30)
    top_hours_colour: ColourField = '#FFFFFF'
    top_text_sep: NumberField = 5

    # Other page constants
    other_bg_path: AssetPathField = "leaderboard/other_page_background.png"
    other_header_height: NumberField = 276
    other_header_gap: NumberField = 20

    # Entry constants
    entry_position_font: FontField = ("SemiBold", 45)
    entry_position_colour: ColourField = '#FFFFFF'
    entry_position_highlight_colour: ColourField = '#FFFFFF'
    entry_name_highlight_colour: ColourField = '#FFFFFF'
    entry_hours_highlight_colour: ColourField = '#FFFFFF'
    entry_name_font: FontField = ("SemiBold", 45)
    entry_name_colour: ColourField = '#FFFFFF'
    entry_hours_font: FontField = ("SemiBold", 45)
    entry_hours_colour: ColourField = '#FFFFFF'
    entry_position_at: NumberField = 200
    entry_name_at: NumberField = 300
    entry_time_at: NumberField = -150

    entry_mask: AssetField = "leaderboard/entry_avatar_mask.png"

    entry_bg_mask: AssetField = "leaderboard/entry_bg_mask.png"
    entry_bg_colour: ColourField = "#162D3C"
    entry_bg_highlight_colour: ColourField = "#0D4865"

    entry_bg: BlobField = FieldDesc(
        BlobField,
        mask_field='entry_bg_mask',
        colour_field='entry_bg_colour',
        colour_override_field=None
    )
    entry_highlight_bg: BlobField = FieldDesc(
        BlobField,
        mask_field='entry_bg_mask',
        colour_field='entry_bg_highlight_colour',
        colour_override_field=None
    )

    entry_gap: NumberField = 13


class LeaderboardPage(Layout):
    def __init__(self, skin, server_name, entries, highlight=None):
        self.skin = skin

        self.server_name = server_name
        self.entries = entries
        self.highlight = highlight
        self.first_page = any(entry.position in (1, 2, 3) for entry in entries)

        self.image = None

    def draw(self) -> Image:
        if self.first_page:
            self.image = self._draw_first_page()
        else:
            self.image = self._draw_other_page()
        return self.image

    def _draw_first_page(self) -> Image:
        # Collect background
        image = Image.open(self.skin.first_bg_path)
        draw = ImageDraw.Draw(image)

        xpos, ypos = 0, 0

        # Draw the header text
        ypos += self.skin.header_text_pre_gap
        header = self._draw_header_text()
        image.alpha_composite(
            header,
            (xpos + (image.width // 2 - header.width // 2),
             ypos)
        )
        ypos += header.height + self.skin.header_gap

        # Draw the top 3
        first_entry = self.entries[0]
        first = self._draw_first(first_entry, level=1)
        first_x = (image.width - first.width) // 2
        image.alpha_composite(
            first,
            (first_x, ypos)
        )
        first_text_y = ypos + first.height + self.skin.first_top_gap
        text_y = first_text_y
        text_x = first_x + (first.width // 2)
        draw.text(
            (text_x, text_y),
            '1ST',
            font=self.skin.top_position_font,
            fill=self.skin.top_position_colour,
            anchor='mt'
        )
        text_y += self.skin.top_name_font.getsize('1ST')[1] + self.skin.top_text_sep
        draw.text(
            (text_x, text_y),
            first_entry.name,
            font=self.skin.top_name_font,
            fill=self.skin.top_name_colour,
            anchor='mt'
        )
        text_y += self.skin.top_name_font.getsize(first_entry.name)[1] + self.skin.top_text_sep
        draw.text(
            (text_x, text_y),
            "{} hours".format(first_entry.time // 3600),
            font=self.skin.top_hours_font,
            fill=self.skin.top_hours_colour,
            anchor='mt'
        )

        if len(self.entries) >= 2:
            second_entry = self.entries[1]
            second = self._draw_first(second_entry, level=2)
            second_x = image.width // 4 - second.width // 2
            image.alpha_composite(
                second,
                (
                    second_x,
                    ypos + (first.height - second.height) // 2
                )
            )
            text_y = first_text_y
            text_x = second_x + (second.width // 2)
            draw.text(
                (text_x, text_y),
                '2ND',
                font=self.skin.top_position_font,
                fill=self.skin.top_position_colour,
                anchor='mt'
            )
            text_y += self.skin.top_name_font.getsize('2ND')[1] + self.skin.top_text_sep
            draw.text(
                (text_x, text_y),
                second_entry.name,
                font=self.skin.top_name_font,
                fill=self.skin.top_name_colour,
                anchor='mt'
            )
            text_y += self.skin.top_name_font.getsize(second_entry.name)[1] + self.skin.top_text_sep
            draw.text(
                (text_x, text_y),
                "{} hours".format(second_entry.time // 3600),
                font=self.skin.top_hours_font,
                fill=self.skin.top_hours_colour,
                anchor='mt'
            )

        if len(self.entries) >= 3:
            third_entry = self.entries[2]
            third = self._draw_first(third_entry, level=3)
            third_x = 3 * image.width // 4 - third.width // 2
            image.alpha_composite(
                third,
                (
                    third_x,
                    ypos + (first.height - third.height) // 2
                )
            )
            text_y = first_text_y
            text_x = third_x + (third.width // 2)
            draw.text(
                (text_x, text_y),
                '3RD',
                font=self.skin.top_position_font,
                fill=self.skin.top_position_colour,
                anchor='mt'
            )
            text_y += self.skin.top_name_font.getsize('3ND')[1] + self.skin.top_text_sep
            draw.text(
                (text_x, text_y),
                third_entry.name,
                font=self.skin.top_name_font,
                fill=self.skin.top_name_colour,
                anchor='mt'
            )
            text_y += self.skin.top_name_font.getsize(third_entry.name)[1] + self.skin.top_text_sep
            draw.text(
                (text_x, text_y),
                "{} hours".format(third_entry.time // 3600),
                font=self.skin.top_hours_font,
                fill=self.skin.top_hours_colour,
                anchor='mt'
            )

        # Draw the entries
        xpos = (image.width - self.skin.entry_bg_mask.width) // 2
        ypos = self.skin.first_header_height + self.skin.header_bg_gap

        for entry in self.entries[3:]:
            entry_image = self._draw_entry(
                entry,
                highlight=self.highlight and (entry.position == self.highlight)
            )
            image.alpha_composite(
                entry_image,
                (xpos, ypos)
            )
            ypos += self.skin.entry_bg_mask.height + self.skin.entry_gap

        return image

    def _draw_other_page(self) -> Image:
        # Collect background
        image = Image.open(self.skin.other_bg_path).convert('RGBA')

        # Draw header onto background
        header = self._draw_header_text()
        image.alpha_composite(
            header,
            (
                (image.width - header.width) // 2,
                (self.skin.other_header_height - header.height) // 2
            )
        )

        # Draw the entries
        xpos = (image.width - self.skin.entry_bg.width) // 2
        ypos = (
            image.height - 10 * self.skin.entry_bg.height - 9 * self.skin.entry_gap
            + self.skin.other_header_height - self.skin.other_header_gap
        ) // 2

        for entry in self.entries:
            entry_image = self._draw_entry(
                entry,
                highlight=self.highlight and (entry.position == self.highlight)
            )
            image.alpha_composite(
                entry_image,
                (xpos, ypos)
            )
            ypos += self.skin.entry_bg.height + self.skin.entry_gap

        return image

    def _draw_entry(self, entry, highlight=False) -> Image:
        # Get the appropriate background
        image = (self.skin.entry_bg if not highlight else self.skin.entry_highlight_bg).copy()
        draw = ImageDraw.Draw(image)
        ypos = image.height // 2

        # Mask the avatar, if it exists
        avatar = entry.image
        avatar.thumbnail((187, 187))
        avatar.paste((0, 0, 0, 0), mask=self.skin.entry_mask)

        # Paste avatar onto image
        image.alpha_composite(avatar, (0, 0))

        # Write position
        draw.text(
            (self.skin.entry_position_at, ypos),
            str(entry.position),
            fill=self.skin.entry_position_highlight_colour if highlight else self.skin.entry_position_colour,
            font=self.skin.entry_position_font,
            anchor='mm'
        )

        # Write name
        draw.text(
            (self.skin.entry_name_at, ypos),
            entry.name,
            fill=self.skin.entry_name_highlight_colour if highlight else self.skin.entry_name_colour,
            font=self.skin.entry_name_font,
            anchor='lm'
        )

        # Write time
        time_str = "{:02d}:{:02d}".format(
            entry.time // 3600,
            (entry.time % 3600) // 60
        )
        draw.text(
            (image.width + self.skin.entry_time_at, ypos),
            time_str,
            fill=self.skin.entry_hours_highlight_colour if highlight else self.skin.entry_hours_colour,
            font=self.skin.entry_hours_font,
            anchor='mm'
        )

        return image

    def _draw_first(self, entry, level) -> Image:
        if level == 1:
            image = self.skin.first_avatar_bg
        elif level == 2:
            image = self.skin.second_avatar_bg
        elif level == 3:
            image = self.skin.third_avatar_bg

        # Retrieve and mask avatar
        avatar = entry.image
        avatar.paste((0, 0, 0, 0), mask=self.skin.first_avatar_mask)

        # Resize for background with gap
        dest_width = image.width - 2 * self.skin.first_avatar_gap
        avatar.thumbnail((dest_width, dest_width))

        # Paste on the background
        image.alpha_composite(
            avatar.convert('RGBA'),
            (
                (image.width - avatar.width) // 2,
                image.height - self.skin.first_avatar_gap - avatar.height)
        )

        return image

    def _draw_header_text(self) -> Image:
        image = Image.new(
            'RGBA',
            (self.skin.header_text_size[0],
             self.skin.header_text_size[1] + self.skin.header_text_gap + self.skin.header_text_line_width
             + self.skin.header_text_line_gap
             + self.skin.subheader_name_font.getsize("THIS MONTHghjyp")[1]),
        )
        draw = ImageDraw.Draw(image)
        xpos, ypos = 0, 0

        # Draw the top text
        draw.text(
            (0, 0),
            self.skin.header_text,
            font=self.skin.header_text_font,
            fill=self.skin.header_text_colour
        )
        ypos += self.skin.header_text_size[1] + self.skin.header_text_gap

        # Draw the underline
        # draw.line(
        #     (xpos, ypos,
        #      xpos + self.skin.header_text_size[0], ypos),
        #     fill=self.skin.header_text_colour,
        #     width=self.skin.header_text_line_width
        # )
        # ypos += self.skin.header_text_line_gap

        # Draw the subheader
        text_name = "SERVER: "
        text_name_width = self.skin.subheader_name_font.getlength(text_name)
        text_value = self.server_name
        text_value_width = self.skin.subheader_value_font.getlength(text_value)
        total_width = text_name_width + text_value_width
        xpos += (image.width - total_width) // 2
        draw.text(
            (xpos, ypos),
            text_name,
            fill=self.skin.subheader_name_colour,
            font=self.skin.subheader_name_font
        )
        xpos += text_name_width
        draw.text(
            (xpos, ypos),
            text_value,
            fill=self.skin.subheader_value_colour,
            font=self.skin.subheader_value_font
        )

        return image


class LeaderboardCard(Card):
    route = 'leaderboard_card'
    card_id = 'leaderboard'

    layout = LeaderboardPage
    skin = LeaderboardSkin

    display_name = "Leaderboard"

    @classmethod
    async def card_route(cls, runner, args, kwargs):
        entries = [LeaderboardEntry(*entry) for entry in kwargs['entries']]
        await asyncio.gather(
            *(entry.get_avatar() for entry in entries)
        )
        kwargs['entries'] = entries
        return await super().card_route(runner, args, kwargs)

    @classmethod
    def _execute(cls, *args, **kwargs):
        for entry in kwargs['entries']:
            entry.convert_avatar()
        return super()._execute(*args, **kwargs)

    @classmethod
    async def sample_args(cls, ctx, **kwargs):
        from ..utils import get_avatar_key

        return {
            'server_name': (ctx.guild.name if ctx.guild else f"{ctx.author.name}'s DMs") if ctx else "No Server",
            'entries': [
                (
                    (ctx.author.id, 1, 1474481, ctx.author.name, get_avatar_key(ctx.client, ctx.author.id))
                    if ctx else
                    (0, 1, 1474481, "John Doe", (0, None))
                ),
                (1, 2, 1445975, 'Abioye', (0, None)),
                (2, 3, 1127296, 'Lacey', (0, None)),
                (3, 4, 1112495, 'Chesed', (0, None)),
                (4, 5, 854514, 'Almas', (0, None)),
                (5, 6, 824414, 'Uche', (0, None)),
                (6, 7, 634560, 'Boitumelo', (0, None)),
                (7, 8, 540633, 'Abimbola', (0, None)),
                (8, 9, 417487, 'Keone', (0, None)),
                (9, 10, 257274, 'Desta', (0, None))
            ],
            'highlight': 4
        }
