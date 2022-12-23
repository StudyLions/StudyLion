from io import BytesIO
import pickle

from PIL import Image, ImageDraw

from ..base import Card, Layout, fielded, Skin, FieldDesc
from ..base.Avatars import avatar_manager
from ..base.Skin import (
    AssetField, StringField, NumberField,
    FontField, ColourField, PointField, ComputedField
)

from .mixins import MiniProfileLayout


@fielded
class TasklistSkin(Skin):
    _env = {
        'scale': 2  # General size scale to match background resolution
    }

    # First page
    first_page_bg: AssetField = "tasklist/first_page_background.png"
    first_page_frame: AssetField = "tasklist/first_page_frame.png"

    title_pre_gap: NumberField = 40
    title_text: StringField = "TO DO LIST"
    title_font: FontField = ('ExtraBold', 76)
    title_size: ComputedField = lambda skin: skin.title_font.getsize(skin.title_text)
    title_colour: ColourField = '#DDB21D'
    title_underline_gap: NumberField = 10
    title_underline_width: NumberField = 5
    title_gap: NumberField = 50

    # Profile section
    mini_profile_indent: NumberField = 125
    mini_profile_size: ComputedField = lambda skin: (
        skin.first_page_bg.width - 2 * skin.mini_profile_indent,
        int(skin._env['scale'] * 200)
    )
    mini_profile_avatar_mask: AssetField = FieldDesc(AssetField, 'mini-profile/avatar_mask.png', convert=None)
    mini_profile_avatar_frame: AssetField = FieldDesc(AssetField, 'mini-profile/avatar_frame.png', convert='RGBA')
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

    # Other pages
    other_page_bg: AssetField = "tasklist/other_page_background.png"
    other_page_frame: AssetField = "tasklist/other_page_frame.png"

    # Help frame
    help_frame: AssetField = "tasklist/help_frame.png"

    # Tasks
    task_start_position: PointField = (100, 75)

    task_done_number_bg: AssetField = "tasklist/task_done_bg.png"
    task_done_number_font: FontField = ('Regular', 45)
    task_done_number_colour: ColourField = '#292828'

    task_done_text_font: FontField = ('Regular', 55)
    task_done_text_colour: ColourField = '#686868'

    task_done_line_width: NumberField = 3.5

    task_undone_number_bg: AssetField = "tasklist/task_undone_bg.png"
    task_undone_number_font: FontField = ('Regular', 45)
    task_undone_number_colour: ColourField = '#FFFFFF'

    task_undone_text_font: FontField = ('Regular', 55)
    task_undone_text_colour: ColourField = '#FFFFFF'

    task_text_height: ComputedField = lambda skin: skin.task_done_text_font.getsize('TASK')[1]
    task_num_sep: NumberField = 30
    task_inter_gap: NumberField = 32
    task_intra_gap: NumberField = 25

    # Date text
    footer_pre_gap: NumberField = 50
    footer_font: FontField = ('Bold', 28)
    footer_colour: ColourField = '#686868'
    footer_gap: NumberField = 50


class TasklistLayout(Layout, MiniProfileLayout):
    def __init__(self, skin, name, discrim, tasks, date, avatar, badges=()):
        self.skin = skin

        self.data_name = name
        self.data_discrim = discrim
        self.data_avatar = avatar
        self.data_tasks = tasks
        self.data_date = date
        self.data_badges = badges

        self.tasks_drawn = 0
        self.images = []

    def _execute_draw(self):
        image_data = []
        for image in self.draw():
            with BytesIO() as data:
                image.save(data, format='PNG')
                data.seek(0)
                image_data.append(data.getvalue())
        return pickle.dumps(image_data)

    def draw(self):
        self.images = []
        self.images.append(self._draw_first_page())
        while self.tasks_drawn < len(self.data_tasks):
            self.images.append(self._draw_another_page())

        return self.images

    def close(self):
        if self.images:
            for image in self.images:
                image.close()

    def _draw_first_page(self) -> Image:
        image = self.skin.first_page_bg
        draw = ImageDraw.Draw(image)
        xpos, ypos = 0, 0

        # Draw header text
        xpos = (image.width - self.skin.title_size[0]) // 2
        ypos += self.skin.title_pre_gap
        draw.text(
            (xpos, ypos),
            self.skin.title_text,
            fill=self.skin.title_colour,
            font=self.skin.title_font
        )

        # Underline it
        ypos += self.skin.title_size[1] + self.skin.title_underline_gap
        # draw.line(
        #     (xpos, ypos, xpos + self.skin.title_size[0], ypos),
        #     fill=self.skin.title_colour,
        #     width=self.skin.title_underline_width
        # )
        ypos += self.skin.title_underline_width + self.skin.title_gap

        # Draw the profile
        xpos = self.skin.mini_profile_indent
        profile = self._draw_profile()
        image.alpha_composite(
            profile,
            (xpos, ypos)
        )

        # Start from the bottom
        ypos = image.height

        if self.data_tasks:
            # Draw the date text
            ypos -= self.skin.footer_gap
            date_text = self.data_date.strftime("As of %d %b")
            size = self.skin.footer_font.getsize(date_text)
            ypos -= size[1]
            draw.text(
                ((image.width - size[0]) // 2, ypos),
                date_text,
                font=self.skin.footer_font,
                fill=self.skin.footer_colour
            )
            ypos -= self.skin.footer_pre_gap

            # Draw the tasks
            task_image = self._draw_tasks_into(self.skin.first_page_frame.copy())

            ypos -= task_image.height
            image.alpha_composite(
                task_image,
                ((image.width - task_image.width) // 2, ypos)
            )
        else:
            # Draw the help frame
            ypos -= self.skin.footer_gap
            image.alpha_composite(
                self.skin.help_frame,
                ((image.width - self.skin.help_frame.width) // 2, ypos - self.skin.help_frame.height)
            )

        return image

    def _draw_another_page(self) -> Image:
        image = self.skin.other_page_bg.copy()
        draw = ImageDraw.Draw(image)

        # Start from the bottom
        ypos = image.height

        # Draw the date text
        ypos -= self.skin.footer_gap
        date_text = self.data_date.strftime("As of %d %b • {} {}".format(self.data_name, self.data_discrim))
        size = self.skin.footer_font.getsize(date_text)
        ypos -= size[1]
        draw.text(
            ((image.width - size[0]) // 2, ypos),
            date_text,
            font=self.skin.footer_font,
            fill=self.skin.footer_colour
        )
        ypos -= self.skin.footer_pre_gap

        # Draw the tasks
        task_image = self._draw_tasks_into(self.skin.other_page_frame.copy())
        ypos -= task_image.height
        image.alpha_composite(
            task_image,
            ((image.width - task_image.width) // 2, ypos)
        )
        return image

    def _draw_tasks_into(self, image) -> Image:
        """
        Draw as many tasks as possible into the given image background.
        """
        draw = ImageDraw.Draw(image)
        xpos, ypos = self.skin.task_start_position

        for n, task, done in self.data_tasks[self.tasks_drawn:]:
            # Draw task first to check if it fits on the page
            task_image = self._draw_text(
                task,
                image.width - xpos - self.skin.task_done_number_bg.width - self.skin.task_num_sep,
                done
            )
            if task_image.height + ypos + self.skin.task_inter_gap > image.height:
                break

            # Draw number background
            bg = self.skin.task_done_number_bg if done else self.skin.task_undone_number_bg
            image.alpha_composite(
                bg,
                (xpos, ypos)
            )

            # Draw number
            font = self.skin.task_done_number_font if done else self.skin.task_undone_number_font
            colour = self.skin.task_done_number_colour if done else self.skin.task_undone_number_colour
            draw.text(
                (xpos + bg.width // 2, ypos + bg.height // 2),
                str(n),
                fill=colour,
                font=font,
                anchor='mm'
            )

            # Draw text
            image.alpha_composite(
                task_image,
                (xpos + bg.width + self.skin.task_num_sep, ypos - (bg.height - self.skin.task_text_height) // 2)
            )

            ypos += task_image.height + self.skin.task_inter_gap
            self.tasks_drawn += 1

        return image

    def _draw_text(self, task, maxwidth, done) -> Image:
        """
        Draw the text of a given task.
        """
        font = self.skin.task_done_text_font if done else self.skin.task_undone_text_font
        colour = self.skin.task_done_text_colour if done else self.skin.task_undone_text_colour

        # Handle empty tasks
        if not task.strip():
            task = '~'

        # First breakup the text
        lines = []
        line = []
        width = 0
        for word in task.split():
            length = font.getlength(word + ' ')
            if width + length > maxwidth:
                if line:
                    lines.append(' '.join(line))
                    line = []
                width = 0
            line.append(word)
            width += length
        if line:
            lines.append(' '.join(line))

        # Then draw it
        bboxes = [font.getbbox(line) for line in lines]
        heights = [font.getsize(line)[1] for line in lines]
        height = sum(height for height in heights) + (len(lines) - 1) * self.skin.task_intra_gap
        image = Image.new('RGBA', (maxwidth, height))
        draw = ImageDraw.Draw(image)

        x, y = 0, 0
        for line, (x1, y1, x2, y2), height in zip(lines, bboxes, heights):
            draw.text(
                (x, y),
                line,
                fill=colour,
                font=font
            )
            if done:
                # Also strikethrough
                draw.line(
                    (x1, y + y1 + (y2 - y1) // 2, x2, y + y1 + (y2 - y1) // 2),
                    fill=self.skin.task_done_text_colour,
                    width=self.skin.task_done_line_width
                )
            y += height + self.skin.task_intra_gap

        return image


class TasklistCard(Card):
    route = 'tasklist_card'
    card_id = 'tasklist'

    layout = TasklistLayout
    skin = TasklistSkin

    display_name = "Tasklist"

    @classmethod
    async def request(cls, *args, **kwargs):
        data = await super().request(*args, **kwargs)
        return pickle.loads(data)

    @classmethod
    async def card_route(cls, runner, args, kwargs):
        kwargs['avatar'] = await avatar_manager().get_avatar(*kwargs['avatar'], 256)
        return await super().card_route(runner, args, kwargs)

    @classmethod
    def _execute(cls, *args, **kwargs):
        with BytesIO(kwargs['avatar']) as image_data:
            with Image.open(image_data).convert('RGBA') as avatar_image:
                kwargs['avatar'] = avatar_image
                return super()._execute(*args, **kwargs)

    @classmethod
    async def generate_sample(cls, ctx=None, **kwargs):
        from ..utils import image_as_file

        sample_kwargs = await cls.sample_args(ctx)
        cards = await cls.request(**{**sample_kwargs, **kwargs})
        return image_as_file(cards[0], "sample.png")

    @classmethod
    async def sample_args(cls, ctx, **kwargs):
        import datetime
        from ..utils import get_avatar_key

        return {
            'name': ctx.author.name if ctx else "John Doe",
            'discrim': '#' + ctx.author.discriminator if ctx else "#0000",
            'tasks': [
                (0, 'Run 50km', True),
                (1, 'Read 5 books', False),
                (2, 'Renovate bedroom', True),
                (3, 'Learn a new language', False),
                (4, 'Upload a vlog', False),
                (5, 'Bibendum arcu vitae elementum curabitur vitae nunc sed velit', False),
                (6, 'Dictum fusce ut placerat orci', True),
                (7, 'Pharetra vel turpis nunc eget lorem dolor', True)
            ],
            'date': datetime.datetime.now().replace(hour=0, minute=0, second=0),
            'avatar': get_avatar_key(ctx.client, ctx.author.id) if ctx else (0, None),
            'badges': (
                'STUDYING: MEDICINE',
                'HOBBY: MATHS',
                'CAREER: STUDENT',
                'FROM: EUROPE',
                'LOVES CATS <3'
            ),
        }
