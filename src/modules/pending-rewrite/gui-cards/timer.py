import math
from io import BytesIO
from PIL import Image, ImageDraw, ImageOps

from ..base import Card, Layout, fielded, Skin
from ..base.Avatars import avatar_manager
from ..base.Skin import (
    AssetField, StringField, NumberField,
    FontField, ColourField, PointField, ComputedField
)


@fielded
class _TimerSkin(Skin):
    _env = {
        'scale': 2  # General size scale to match background resolution
    }

    background: AssetField = "timer/background.png"
    main_colour: ColourField

    header_field_height: NumberField = 171.5
    header_font: FontField = ('ExtraBold', 76)

    inner_margin: NumberField = 40
    inner_sep: NumberField = 7.5

    # Timer section
    # Outer progress bar
    progress_end: AssetField
    progress_start: AssetField
    progress_bg: AssetField = "timer/break_timer.png"
    progress_mask: ComputedField = lambda skin: ImageOps.invert(skin.progress_bg.split()[-1].convert('L'))

    timer_bg: AssetField = "timer/timer_bg.png"

    # Inner timer text
    countdown_font: FontField = ('Light', 112)
    countdown_gap: NumberField = 10
    stage_font: FontField = ('Light', 43.65)
    stage_colour: ColourField = '#FFFFFF'

    mic_icon: AssetField
    stage_text: StringField

    # Members
    user_bg: AssetField = "timer/break_user.png"
    user_mask: AssetField = "timer/avatar_mask.png"

    time_font: FontField = ('Black', 26)
    time_colour: ColourField = '#FFFFFF'

    tag_gap: NumberField = 5.5
    tag: AssetField
    tag_font: FontField = ('SemiBold', 25)

    # grid_x = (background.width - progress_mask.width - 2 * progress_end.width - grid_start[0] - user_bg.width) // 4
    grid: PointField = (344, 246)

    # Date text
    date_font: FontField = ('Bold', 28)
    date_colour: ColourField = '#6f6e6f'
    date_gap: NumberField = 50


@fielded
class FocusTimerSkin(_TimerSkin):
    main_colour: ColourField = '#DDB21D'
    user_bg: AssetField = "timer/focus_user.png"
    mic_icon: AssetField = "timer/mute.png"
    progress_end: AssetField = "timer/progress_end_focus.png"
    progress_start: AssetField = "timer/progress_start_focus.png"
    stage_text: StringField = "FOCUS"
    tag: AssetField = "timer/focus_tag.png"


@fielded
class BreakTimerSkin(_TimerSkin):
    main_colour: ColourField = '#78B7EF'
    user_bg: AssetField = "timer/break_user.png"
    mic_icon: AssetField = "timer/unmute.png"
    progress_end: AssetField = "timer/progress_end_break.png"
    progress_start: AssetField = "timer/progress_start_break.png"
    stage_text: StringField = "BREAK"
    tag: AssetField = "timer/break_tag.png"


class TimerLayout(Layout):
    def __init__(self, skin, name, remaining, duration, users):
        self.skin = skin

        self.data_name = name
        self.data_remaining = 5 * math.ceil(remaining / 5)
        self.data_duration = duration
        self.data_amount = 1 - remaining / duration
        self.data_users = sorted(users, key=lambda user: user[1], reverse=True)  # (avatar, time)

    @staticmethod
    def format_time(time, hours=True):
        if hours:
            return "{:02}:{:02}".format(int(time // 3600), int((time // 60) % 60))
        else:
            return "{:02}:{:02}".format(int(time // 60), int(time % 60))

    def draw(self):
        image = self.skin.background
        draw = ImageDraw.Draw(image)

        # Draw header
        text = self.data_name
        length = self.skin.header_font.getlength(text)
        draw.text(
            (image.width // 2, self.skin.header_field_height // 2),
            text,
            fill=self.skin.main_colour,
            font=self.skin.header_font,
            anchor='mm'
        )

        # Draw timer
        timer_image = self._draw_progress_bar(self.data_amount)
        ypos = timer_y = (
            self.skin.header_field_height
            + (image.height - self.skin.header_field_height - timer_image.height) // 2
            - self.skin.progress_end.height // 2
        )
        xpos = timer_x = image.width - self.skin.inner_margin - timer_image.width

        image.alpha_composite(
            timer_image,
            (xpos, ypos)
        )

        # Draw timer text
        stage_size = self.skin.stage_font.getsize(' ' + self.skin.stage_text)

        ypos += timer_image.height // 2 - stage_size[1] // 2
        xpos += timer_image.width // 2
        draw.text(
            (xpos, ypos),
            (text := self.format_time(self.data_remaining)),
            fill=self.skin.main_colour,
            font=self.skin.countdown_font,
            anchor='mm'
        )

        size = int(self.skin.countdown_font.getsize(text)[1])
        ypos += size

        self.skin.mic_icon.thumbnail((stage_size[1], stage_size[1]))
        length = int(self.skin.mic_icon.width + self.skin.stage_font.getlength(' ' + self.skin.stage_text))
        xpos -= length // 2

        image.alpha_composite(
            self.skin.mic_icon,
            (xpos, ypos - self.skin.mic_icon.height)
        )
        draw.text(
            (xpos + self.skin.mic_icon.width, ypos),
            ' ' + self.skin.stage_text,
            fill=self.skin.stage_colour,
            font=self.skin.stage_font,
            anchor='ls'
        )

        # Draw user grid
        if self.data_users:
            grid_image = self.draw_user_grid()

            # ypos = self.skin.header_field_height + (image.height - self.skin.header_field_height - grid_image.height) // 2
            ypos = timer_y + (timer_image.height - grid_image.height) // 2 - stage_size[1] // 2
            xpos = (
                self.skin.inner_margin
                + (timer_x - self.skin.inner_sep - self.skin.inner_margin) // 2
                - grid_image.width // 2
            )

            image.alpha_composite(
                grid_image,
                (xpos, ypos)
            )

        # Draw the footer
        ypos = image.height
        ypos -= self.skin.date_gap
        date_text = "Use !now [text] to show what you are working on!"
        size = self.skin.date_font.getsize(date_text)
        ypos -= size[1]
        draw.text(
            ((image.width - size[0]) // 2, ypos),
            date_text,
            font=self.skin.date_font,
            fill=self.skin.date_colour
        )
        return image

    def draw_user_grid(self) -> Image:
        users = list(self.data_users)[:25]

        # Set these to 5 and 5 to force top left corner
        rows = math.ceil(len(users) / 5)
        columns = 5
        # columns = min(len(users), 5)

        size = (
            (columns - 1) * self.skin.grid[0] + self.skin.user_bg.width,
            (rows - 1) * self.skin.grid[1] + self.skin.user_bg.height + self.skin.tag_gap + self.skin.tag.height
        )

        image = Image.new(
            'RGBA',
            size
        )
        for i, user in enumerate(users):
            x = (i % 5) * self.skin.grid[0]
            y = (i // 5) * self.skin.grid[1]

            user_image = self.draw_user(user)
            image.alpha_composite(
                user_image,
                (x, y)
            )
        return image

    def draw_user(self, user):
        width = self.skin.user_bg.width
        height = self.skin.user_bg.height + self.skin.tag_gap + self.skin.tag.height
        image = Image.new('RGBA', (width, height))
        draw = ImageDraw.Draw(image)

        image.alpha_composite(self.skin.user_bg)

        avatar, time, tag = user
        avatar = avatar
        timestr = self.format_time(time, hours=True)

        # Mask avatar
        avatar.paste((0, 0, 0, 0), mask=self.skin.user_mask.convert('RGBA'))

        # Resize avatar
        avatar.thumbnail((self.skin.user_bg.height - 10, self.skin.user_bg.height - 10))

        image.alpha_composite(
            avatar,
            (5, 5)
        )
        draw.text(
            (120, self.skin.user_bg.height // 2),
            timestr,
            anchor='lm',
            font=self.skin.time_font,
            fill=self.skin.time_colour
        )

        if tag:
            ypos = self.skin.user_bg.height + self.skin.tag_gap
            image.alpha_composite(
                self.skin.tag,
                ((image.width - self.skin.tag.width) // 2, ypos)
            )
            draw.text(
                (image.width // 2, ypos + self.skin.tag.height // 2),
                tag,
                font=self.skin.tag_font,
                fill='#FFFFFF',
                anchor='mm'
            )
        return image

    def _draw_progress_bar(self, amount):
        amount = min(amount, 1)
        amount = max(amount, 0)
        bg = self.skin.timer_bg
        end = self.skin.progress_start
        mask = self.skin.progress_mask

        center = (
            bg.width // 2 + 1,
            bg.height // 2
        )
        radius = 553
        theta = amount * math.pi * 2 - math.pi / 2
        x = int(center[0] + radius * math.cos(theta))
        y = int(center[1] + radius * math.sin(theta))

        canvas = Image.new('RGBA', size=(bg.width, bg.height))
        draw = ImageDraw.Draw(canvas)

        if amount >= 0.01:
            canvas.alpha_composite(
                end,
                (
                    center[0] - end.width // 2,
                    26 - end.height // 2
                )
            )

            sidelength = bg.width // 2
            line_ends = (
                int(center[0] + sidelength * math.cos(theta)),
                int(center[1] + sidelength * math.sin(theta))
            )
            if amount <= 0.25:
                path = [
                    center,
                    (center[0], center[1] - sidelength),
                    (bg.width, 0),
                    line_ends
                ]
            elif amount <= 0.5:
                path = [
                    center,
                    (center[0], center[1] - sidelength),
                    (bg.width, 0),
                    (bg.width, bg.height),
                    line_ends
                ]
            elif amount <= 0.75:
                path = [
                    center,
                    (center[0], center[1] - sidelength),
                    (bg.width, 0),
                    (bg.width, bg.height),
                    (0, bg.height),
                    line_ends
                ]
            else:
                path = [
                    center,
                    (center[0], center[1] - sidelength),
                    (bg.width, 0),
                    (bg.width, bg.height),
                    (0, bg.height),
                    (0, 0),
                    line_ends
                ]

            draw.polygon(
                path,
                fill=self.skin.main_colour
            )

            canvas.paste((0, 0, 0, 0), mask=mask)

        image = Image.new(
            'RGBA',
            size=(bg.width + self.skin.progress_end.width,
                  bg.height + self.skin.progress_end.height)
        )
        image.alpha_composite(
            bg,
            (self.skin.progress_end.width // 2,
             self.skin.progress_end.height // 2)
        )
        image.alpha_composite(
            canvas,
            (self.skin.progress_end.width // 2,
             self.skin.progress_end.height // 2)
        )

        image.alpha_composite(
            self.skin.progress_end,
            (
                x,
                y
            )
        )

        return image


class _TimerCard(Card):
    layout = TimerLayout

    @classmethod
    async def card_route(cls, runner, args, kwargs):
        if kwargs['users']:
            avatar_keys, times, tags = zip(*kwargs['users'])
            avatars = await avatar_manager().get_avatars(*((*key, 512) for key in avatar_keys))
            kwargs['users'] = tuple(zip(avatars, times, tags))

        return await super().card_route(runner, args, kwargs)

    @classmethod
    def _execute(cls, *args, **kwargs):
        if kwargs['users']:
            avatar_data, times, tags = zip(*kwargs['users'])
            avatars = []
            for datum in avatar_data:
                with BytesIO(datum) as buffer:
                    buffer.seek(0)
                    avatars.append(Image.open(buffer).convert('RGBA'))
            kwargs['users'] = tuple(zip(avatars, times, tags))

        return super()._execute(*args, **kwargs)


class FocusTimerCard(_TimerCard):
    route = 'focus_timer_card'
    card_id = 'focus_timer'

    skin = FocusTimerSkin
    display_name = "Focus Timer"

    @classmethod
    async def sample_args(cls, ctx, **kwargs):
        from ..utils import get_avatar_key

        return {
            'name': 'Pomodoro Timer',
            'remaining': 1658,
            'duration': 3000,
            'users': [
                (get_avatar_key(ctx.client, ctx.author.id), 7055, "SkinShop"),
                ((0, None), 6543, "Never"),
                ((0, None), 5432, "Going"),
                ((0, None), 4321, "To"),
                ((0, None), 3210, "Give"),
                ((0, None), 2109, "You"),
                ((0, None), 1098, "Up"),
            ]
        }


class BreakTimerCard(_TimerCard):
    route = 'break_timer_card'
    card_id = 'break_timer'

    skin = BreakTimerSkin
    display_name = "Break Timer"

    @classmethod
    async def sample_args(cls, ctx, **kwargs):
        from ..utils import get_avatar_key

        return {
            'name': 'Pomodoro Timer',
            'remaining': 1658,
            'duration': 3000,
            'users': [
                (get_avatar_key(ctx.client, ctx.author.id), 7055, "SkinShop"),
                ((0, None), 6543, "Never"),
                ((0, None), 5432, "Going"),
                ((0, None), 4321, "To"),
                ((0, None), 3210, "Let"),
                ((0, None), 2109, "You"),
                ((0, None), 1098, "Down"),
            ]
        }
