import asyncio
import datetime as dt
from src.cards import StatsCard


highlights = [
    'header_colour',
    'stats_subheader_colour',
    'stats_text_colour',
    'col2_date_colour',
    'col2_hours_colour',
    'cal_weekday_colour',
    'cal_number_colour',
    'cal_number_end_colour',
    'cal_streak_end_colour',
    'cal_streak_middle_colour',
]
highlight_colour = "#E84727"


async def get_cards():
    for highlight in highlights:
        card = await StatsCard.generate_sample(
            skin={highlight: highlight_colour}
        )
        with open('../skins/spec/images/stats/{}.png'.format(highlight), 'wb') as image_file:
            image_file.write(card.fp.read())

if __name__ == '__main__':
    asyncio.run(get_cards())
