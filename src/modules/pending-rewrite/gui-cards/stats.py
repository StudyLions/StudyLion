import itertools
from datetime import datetime, timedelta
from PIL import Image, ImageDraw

from ..base import Card, Layout, fielded, Skin
from ..base.Skin import (
    AssetField, BlobField, StringField, NumberField, RawField,
    FontField, ColourField, PointField, ComputedField, FieldDesc
)


def format_lb(pos):
    """
    Format a leaderboard position into a string.
    """
    if pos is None:
        return 'Unranked'

    if pos % 10 == 1 and pos % 100 != 11:
        return f"{pos}ST"

    if pos % 10 == 2 and pos % 100 != 12:
        return f"{pos}ND"

    if pos % 10 == 3 and pos % 100 != 13:
        return f"{pos}RD"

    return f"{pos}TH"


def format_time(seconds):
    return "{:02}:{:02}".format(
        int(seconds // 3600),
        int(seconds % 3600 // 60)
    )


@fielded
class StatsSkin(Skin):
    _env = {
        'scale': 2  # General size scale to match background resolution
    }

    # Background images
    background: AssetField = "stats/background.png"

    # Inner container
    container_position: PointField = (60, 50)  # Position of top left corner
    container_size: PointField = (1410, 800)  # Size of the inner container

    # Major (topmost) header
    header_font: FontField = ('Black', 27)
    header_colour: ColourField = '#DDB21D'
    header_gap: NumberField = 35  # Gap between header and column contents
    header_height: ComputedField = lambda skin: skin.header_font.getsize('STATISTICS')[1]

    # First column
    col1_header: StringField = 'STATISTICS'
    stats_subheader_pregap: NumberField = 8
    stats_subheader_font: FontField = ('Black', 21)
    stats_subheader_colour: ColourField = '#FFFFFF'
    stats_subheader_size: ComputedField = lambda skin: skin.stats_subheader_font.getsize('LEADERBOARD POSITION')
    stats_text_gap: NumberField = 13  # Gap between stat lines
    stats_text_font: FontField = ('SemiBold', 19)
    stats_text_height: ComputedField = lambda skin: skin.stats_text_font.getsize('DAILY')[1]
    stats_text_colour: ColourField = '#BABABA'

    col1_size: ComputedField = lambda skin: (
        skin.stats_subheader_size[0],
        skin.header_height + skin.header_gap
        + 3 * skin.stats_subheader_size[1]
        + 2 * skin.stats_subheader_pregap
        + 6 * skin.stats_text_height
        + 8 * skin.stats_text_gap
    )

    # Second column
    col2_header: StringField = 'STUDY STREAK'
    col2_date_font: FontField = ('Black', 21)
    col2_date_colour: ColourField = '#FFFFFF'
    col2_hours_colour: ColourField = '#1473A2'
    col2_date_gap: NumberField = 25  # Gap between date line and calender
    col2_subheader_height: ComputedField = lambda skin: skin.col2_date_font.getsize('JANUARY')[1]
    cal_column_sep: NumberField = 35
    cal_weekday_text: RawField = ('S', 'M', 'T', 'W', 'T', 'F', 'S')
    cal_weekday_font: FontField = ('ExtraBold', 21)
    cal_weekday_colour: ColourField = '#FFFFFF'
    cal_weekday_height: ComputedField = lambda skin: skin.cal_weekday_font.getsize('S')[1]
    cal_weekday_gap: NumberField = 23
    cal_number_font: FontField = ('Medium', 20)
    cal_number_end_colour: ColourField = '#BABABA'
    cal_number_colour: ColourField = '#BABABA'
    cal_number_gap: NumberField = 28
    alt_cal_number_gap: NumberField = 20
    cal_number_size: ComputedField = lambda skin: skin.cal_number_font.getsize('88')

    cal_streak_mask: AssetField = 'stats/streak_mask.png'

    cal_streak_end_colour: ColourField = '#1473A2'
    cal_streak_end_colour_override: ColourField = None
    cal_streak_end: BlobField = FieldDesc(
        BlobField,
        mask_field='cal_streak_mask',
        colour_field='cal_streak_end_colour',
        colour_override_field='cal_streak_end_colour_override'
    )

    cal_streak_middle_colour: ColourField = '#1B3343'
    cal_streak_middle_colour_override: ColourField = None
    cal_streak_middle: BlobField = FieldDesc(
        BlobField,
        mask_field='cal_streak_mask',
        colour_field='cal_streak_middle_colour',
        colour_override_field='cal_streak_middle_colour_override'
    )

    cal_size: ComputedField = lambda skin: (
        7 * skin.cal_number_size[0] + 6 * skin.cal_column_sep + skin.cal_streak_end.width // 2,
        5 * skin.cal_number_size[1] + 4 * skin.cal_number_gap
        + skin.cal_weekday_height + skin.cal_weekday_gap
        + skin.cal_streak_end.height // 2
    )

    alt_cal_size: ComputedField = lambda skin: (
        7 * skin.cal_number_size[0] + 6 * skin.cal_column_sep + skin.cal_streak_end.width // 2,
        6 * skin.cal_number_size[1] + 5 * skin.alt_cal_number_gap
        + skin.cal_weekday_height + skin.cal_weekday_gap
        + skin.cal_streak_end.height // 2
    )

    col2_size: ComputedField = lambda skin: (
        skin.cal_size[0],
        skin.header_height + skin.header_gap
        + skin.col2_subheader_height + skin.col2_date_gap
        + skin.cal_size[1]
    )

    alt_col2_size: ComputedField = lambda skin: (
        skin.alt_cal_size[0],
        skin.header_height + skin.header_gap
        + skin.col2_subheader_height + skin.col2_date_gap
        + skin.alt_cal_size[1]
    )


class StatsLayout(Layout):
    def __init__(self, skin, lb_data, time_data, workouts, streak_data, date=None, draft=False, **kwargs):
        self.draft = draft

        self.skin = skin

        self.data_lb_time = lb_data[0]  # Position on time leaderboard, or None
        self.data_lb_lc = lb_data[1]  # Position on coin leaderboard, or None

        self.data_time_daily = int(time_data[0])  # Daily time in seconds
        self.data_time_weekly = int(time_data[1])  # Weekly time in seconds
        self.data_time_monthly = int(time_data[2])  # Monthly time in seconds
        self.data_time_all = int(time_data[3])  # All time in seconds

        self.data_workouts = workouts  # Number of workout sessions
        self.data_streaks = streak_data  # List of streak day ranges to show

        # Extract date info
        date = date if date else datetime.today()  # Date to show for month/year
        month_first_day = date.replace(day=1)
        month_days = (month_first_day.replace(month=(month_first_day.month % 12) + 1) - timedelta(days=1)).day

        self.date = date
        self.month = date.strftime('%B').upper()
        self.first_weekday = month_first_day.weekday()  # Which weekday the month starts on
        self.month_days = month_days
        self.alt_layout = (month_days + self.first_weekday + 1) > 35  # Whether to use the alternate layout

        if self.alt_layout:
            self.skin.fields['cal_number_gap'].value = self.skin.alt_cal_number_gap
            self.skin.fields['cal_size'].value = self.skin.alt_cal_size
            self.skin.fields['col2_size'].value = self.skin.alt_col2_size

        self.image: Image = None  # Final Image

    def draw(self):
        # Load/copy background
        image = self.skin.background

        # Draw inner container
        inner_container = self.draw_inner_container()

        # Paste inner container on background
        image.alpha_composite(inner_container, self.skin.container_position)

        self.image = image
        return image

    def draw_inner_container(self):
        container = Image.new('RGBA', self.skin.container_size)

        col1 = self.draw_column_1()
        col2 = self.draw_column_2()

        container.alpha_composite(col1)
        container.alpha_composite(col2, (container.width - col2.width, 0))

        if self.draft:
            draw = ImageDraw.Draw(container)
            draw.rectangle(((0, 0), (self.skin.container_size[0]-1, self.skin.container_size[1]-1)))

        return container

    def draw_column_1(self) -> Image:
        # Create new image for column 1
        col1 = Image.new('RGBA', self.skin.col1_size)
        draw = ImageDraw.Draw(col1)

        if self.draft:
            draw.rectangle(((0, 0), (self.skin.col1_size[0]-1, self.skin.col1_size[1]-1)))

        # Tracking current drawing height
        position = 0

        # Write header
        draw.text(
            (0, position),
            self.skin.col1_header,
            font=self.skin.header_font,
            fill=self.skin.header_colour
        )
        position += self.skin.header_height + self.skin.header_gap

        # Leaderboard
        draw.text(
            (0, position),
            'LEADERBOARD POSITION',
            font=self.skin.stats_subheader_font,
            fill=self.skin.stats_subheader_colour
        )
        position += self.skin.col2_subheader_height + self.skin.stats_text_gap

        draw.text(
            (0, position),
            f"TIME: {format_lb(self.data_lb_time)}",
            font=self.skin.stats_text_font,
            fill=self.skin.stats_text_colour
        )
        position += self.skin.stats_text_height + self.skin.stats_text_gap

        draw.text(
            (0, position),
            "ANKI: COMING SOON",
            font=self.skin.stats_text_font,
            fill=self.skin.stats_text_colour
        )
        position += self.skin.stats_text_height + self.skin.stats_text_gap

        position += self.skin.stats_subheader_pregap
        # Study time
        draw.text(
            (0, position),
            'STUDY TIME',
            font=self.skin.stats_subheader_font,
            fill=self.skin.stats_subheader_colour
        )
        position += self.skin.col2_subheader_height + self.skin.stats_text_gap

        draw.text(
            (0, position),
            f'DAILY: {format_time(self.data_time_daily)}',
            font=self.skin.stats_text_font,
            fill=self.skin.stats_text_colour
        )
        position += self.skin.stats_text_height + self.skin.stats_text_gap

        draw.text(
            (0, position),
            f'MONTHLY: {format_time(self.data_time_monthly)}',
            font=self.skin.stats_text_font,
            fill=self.skin.stats_text_colour
        )
        position += self.skin.stats_text_height + self.skin.stats_text_gap

        draw.text(
            (0, position),
            f'WEEKLY: {format_time(self.data_time_weekly)}',
            font=self.skin.stats_text_font,
            fill=self.skin.stats_text_colour
        )
        position += self.skin.stats_text_height + self.skin.stats_text_gap

        draw.text(
            (0, position),
            f'ALL TIME: {format_time(self.data_time_all)}',
            font=self.skin.stats_text_font,
            fill=self.skin.stats_text_colour
        )
        position += self.skin.stats_text_height + self.skin.stats_text_gap

        position += self.skin.stats_subheader_size[1] // 2

        position += self.skin.stats_subheader_pregap
        # Workouts
        workout_text = "WORKOUTS: "
        draw.text(
            (0, position),
            workout_text,
            font=self.skin.stats_subheader_font,
            fill=self.skin.stats_subheader_colour,
            anchor='lm'
        )
        xposition = self.skin.stats_subheader_font.getlength(workout_text)
        draw.text(
            (xposition, position),
            str(self.data_workouts),
            font=self.skin.stats_text_font,
            fill=self.skin.stats_subheader_colour,
            anchor='lm'
        )

        return col1

    def draw_column_2(self) -> Image:
        # Create new image for column 1
        col2 = Image.new('RGBA', self.skin.col2_size)
        draw = ImageDraw.Draw(col2)

        if self.draft:
            draw.rectangle(((0, 0), (self.skin.col2_size[0]-1, self.skin.col2_size[1]-1)))

        # Tracking current drawing height
        position = 0

        # Write header
        draw.text(
            (0, position),
            self.skin.col2_header,
            font=self.skin.header_font,
            fill=self.skin.header_colour
        )
        position += self.skin.header_height + self.skin.header_gap

        # Draw date line
        month_text = "{}: ".format(self.month)
        draw.text(
            (0, position),
            month_text,
            font=self.skin.col2_date_font,
            fill=self.skin.col2_date_colour
        )
        xposition = self.skin.col2_date_font.getlength(month_text)
        draw.text(
            (xposition, position),
            f"{self.data_time_monthly // 3600} HRS",
            font=self.skin.col2_date_font,
            fill=self.skin.col2_hours_colour
        )
        year_text = str(self.date.year)
        xposition = col2.width - self.skin.col2_date_font.getlength(year_text)
        draw.text(
            (xposition, position),
            year_text,
            font=self.skin.col2_date_font,
            fill=self.skin.col2_date_colour
        )
        position += self.skin.col2_subheader_height + self.skin.col2_date_gap

        # Draw calendar
        cal = self.draw_calendar()

        col2.alpha_composite(cal, (0, position))

        return col2

    def draw_calendar(self) -> Image:
        cal = Image.new('RGBA', self.skin.cal_size)
        draw = ImageDraw.Draw(cal)

        if self.draft:
            draw.rectangle(((0, 0), (self.skin.cal_size[0]-1, self.skin.cal_size[1]-1)))

        xpos, ypos = (0, 0)  # Approximate position of top left corner to draw on

        # Constant offset to mid basepoint of text
        xoffset = self.skin.cal_streak_end.width // 2
        yoffset = self.skin.cal_number_size[1] // 2

        # Draw the weekdays
        for i, l in enumerate(self.skin.cal_weekday_text):
            draw.text(
                (xpos + xoffset, ypos + yoffset),
                l,
                font=self.skin.cal_weekday_font,
                fill=self.skin.cal_weekday_colour,
                anchor='mm'
            )
            xpos += self.skin.cal_number_size[0] + self.skin.cal_column_sep
        ypos += self.skin.cal_weekday_height + self.skin.cal_weekday_gap
        xpos = 0

        streak_starts = list(itertools.chain(*self.data_streaks))
        streak_middles = list(itertools.chain(*(range(i+1, j) for i, j in self.data_streaks)))
        streak_pairs = set(i for i, j in self.data_streaks if j-i == 1)

        # Draw the days of the month
        num_diff_x = self.skin.cal_number_size[0] + self.skin.cal_column_sep
        num_diff_y = self.skin.cal_number_size[1] + self.skin.cal_number_gap
        offset = (self.first_weekday + 1) % 7

        centres = [
            (xpos + xoffset + (i + offset) % 7 * num_diff_x,
             ypos + yoffset + (i + offset) // 7 * num_diff_y)
            for i in range(0, self.month_days)
        ]

        for day in streak_middles:
            if day < 1:
                continue
            i = day - 1
            if i >= len(centres):
                # Shouldn't happen, but ignore
                continue
            x, y = centres[i]
            week_day = (i + offset) % 7

            top = y - self.skin.cal_streak_end.height // 2
            bottom = y + self.skin.cal_streak_end.height // 2 - 1

            # Middle of streak on edges
            if week_day == 0 or i == 0:
                # Draw end bobble
                cal.paste(
                    self.skin.cal_streak_middle,
                    (x - self.skin.cal_streak_end.width // 2, top)
                )
                if week_day != 6:
                    # Draw rectangle forwards
                    draw.rectangle(
                        ((x, top), (x + num_diff_x, bottom)),
                        fill=self.skin.cal_streak_middle_colour,
                        width=0
                    )
            elif week_day == 6 or i == self.month_days - 1:
                # Draw end bobble
                cal.paste(
                    self.skin.cal_streak_middle,
                    (x - self.skin.cal_streak_end.width // 2, top)
                )
                if week_day != 0:
                    # Draw rectangle backwards
                    draw.rectangle(
                        ((x - num_diff_x, top), (x, bottom)),
                        fill=self.skin.cal_streak_middle_colour,
                        width=0
                    )
            else:
                # Draw rectangle on either side
                draw.rectangle(
                    ((x - num_diff_x, top), (x + num_diff_x, bottom)),
                    fill=self.skin.cal_streak_middle_colour,
                    width=0
                )

        for i, (x, y) in enumerate(centres):
            # Streak endpoint
            if i + 1 in streak_starts:
                if i + 1 in streak_pairs and (i + offset) % 7 != 6:
                    # Draw rectangle forwards
                    top = y - self.skin.cal_streak_end.height // 2
                    bottom = y + self.skin.cal_streak_end.height // 2 - 1
                    draw.rectangle(
                        ((x, top), (x + num_diff_x, bottom)),
                        fill=self.skin.cal_streak_middle_colour,
                        width=0
                    )
                cal.alpha_composite(
                    self.skin.cal_streak_end,
                    (x - self.skin.cal_streak_end.width // 2, y - self.skin.cal_streak_end.height // 2)
                )

        for i, (x, y) in enumerate(centres):
            numstr = str(i + 1)

            draw.text(
                (x, y),
                numstr,
                font=self.skin.cal_number_font,
                fill=self.skin.cal_number_end_colour if (i+1 in streak_starts) else self.skin.cal_number_colour,
                anchor='mm'
            )

        return cal


class StatsCard(Card):
    route = 'stats_card'
    card_id = 'stats'

    layout = StatsLayout
    skin = StatsSkin

    display_name = "User Stats"

    @classmethod
    async def sample_args(cls, ctx, **kwargs):
        return {
            'lb_data': (21, 123),
            'time_data': (3600, 5 * 24 * 3600, 1.5 * 24 * 3600, 100 * 24 * 3600),
            'workouts': 50,
            'streak_data': [(1, 3), (7, 8), (10, 10), (12, 16), (18, 25), (27, 31)],
            'date': datetime(2022, 2, 1)
        }
