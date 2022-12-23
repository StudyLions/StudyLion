from PIL import Image, ImageDraw, ImageOps, ImageColor

from ..base import Card, Layout, fielded, Skin, FieldDesc
from ..base.Avatars import avatar_manager
from ..base.Skin import (
    AssetField, RGBAAssetField, BlobField, AssetPathField, StringField, NumberField,
    FontField, ColourField, PointField, ComputedField
)


@fielded
class MiniProfileSkin(Skin):

    # Profile section
    mini_profile_indent: NumberField = 125
    mini_profile_size: ComputedField = lambda skin: (
        skin.background.width - 2 * skin.mini_profile_indent,
        int(skin._env['scale'] * 200)
    )
    mini_profile_avatar_mask: AssetField = FieldDesc(AssetField, 'mini-profile/avatar_mask.png', convert=None)
    mini_profile_avatar_frame: AssetField = FieldDesc(AssetField, 'mini-profile/avatar_frame.png', convert=None)
    mini_profile_avatar_sep: NumberField = 50

    mini_profile_name_font: FontField = ('BoldItalic', 55)
    mini_profile_name_colour: ColourField = '#DDB21D'
    mini_profile_discrim_font: FontField = mini_profile_name_font
    mini_profile_discrim_colour: ColourField = '#BABABA'
    mini_profile_name_gap: NumberField = 20

    mini_profile_badge_end: AssetField = "mini-profile/badge_end.png"
    mini_profile_badge_font: FontField = ('Black', 30)
    mini_profile_badge_colour: ColourField = '#FFFFFF'
    mini_profile_badge_text_colour: ColourField = '#051822'
    mini_profile_badge_gap: NumberField = 20
    mini_profile_badge_min_sep: NumberField = 10


class MiniProfileLayout:
    def _draw_profile(self) -> Image:
        image = Image.new('RGBA', self.skin.mini_profile_size)
        draw = ImageDraw.Draw(image)
        xpos, ypos = 0, 0

        frame = self.skin.mini_profile_avatar_frame
        if frame.height >= image.height:
            frame.thumbnail((image.height, image.height))

        # Draw avatar
        avatar = self.data_avatar
        avatar.paste((0, 0, 0, 0), mask=self.skin.mini_profile_avatar_mask)
        avatar_image = Image.new('RGBA', frame.size)
        avatar_image.paste(
            avatar,
            (
                (frame.width - avatar.width) // 2,
                (frame.height - avatar.height) // 2
            )
        )
        avatar_image.alpha_composite(frame)
        avatar_image = avatar_image.resize(
            (self.skin.mini_profile_size[1], self.skin.mini_profile_size[1])
        )
        image.alpha_composite(avatar_image, (0, 0))

        xpos += avatar_image.width + self.skin.mini_profile_avatar_sep

        # Draw name
        name_text = self.data_name
        name_length = self.skin.mini_profile_name_font.getlength(name_text + ' ')
        name_height = self.skin.mini_profile_name_font.getsize(name_text)[1]
        draw.text(
            (xpos, ypos),
            name_text,
            fill=self.skin.mini_profile_name_colour,
            font=self.skin.mini_profile_name_font
        )
        draw.text(
            (xpos + name_length, ypos),
            self.data_discrim,
            fill=self.skin.mini_profile_discrim_colour,
            font=self.skin.mini_profile_discrim_font
        )
        ypos += name_height + self.skin.mini_profile_name_gap

        # Draw badges
        _x = 0
        max_x = self.skin.mini_profile_size[0] - xpos

        badges = [self._draw_badge(text) for text in self.data_badges]
        for badge in badges:
            if badge.width + _x > max_x:
                _x = 0
                ypos += badge.height + self.skin.mini_profile_badge_gap
            image.paste(
                badge,
                (xpos + _x, ypos)
            )
            _x += badge.width + self.skin.mini_profile_badge_min_sep
        return image

    def _draw_badge(self, text) -> Image:
        """
        Draw a single profile badge, with the given text.
        """
        text_length = self.skin.mini_profile_badge_font.getsize(text)[0]

        height = self.skin.mini_profile_badge_end.height
        width = text_length + self.skin.mini_profile_badge_end.width

        badge = Image.new('RGBA', (width, height), color=(0, 0, 0, 0))

        # Add blobs to ends
        badge.paste(
            self.skin.mini_profile_badge_end,
            (0, 0)
        )
        badge.paste(
            self.skin.mini_profile_badge_end,
            (width - self.skin.mini_profile_badge_end.width, 0)
        )

        # Add rectangle to middle
        draw = ImageDraw.Draw(badge)
        draw.rectangle(
            (
                (self.skin.mini_profile_badge_end.width // 2, 0),
                (width - self.skin.mini_profile_badge_end.width // 2, height),
            ),
            fill='#FFFFFF',
            width=0
        )
        badge.paste(ImageColor.getrgb(self.skin.mini_profile_badge_colour), mask=badge)

        # Write badge text
        draw.text(
            (self.skin.mini_profile_badge_end.width // 2, height // 2),
            text,
            font=self.skin.mini_profile_badge_font,
            fill=self.skin.mini_profile_badge_text_colour,
            anchor='lm'
        )

        return badge
