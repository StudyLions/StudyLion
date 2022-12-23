import asyncio
import datetime as dt
from src.cards import TasklistCard


highlights = [
    'mini_profile_badge_colour',
    'mini_profile_name_colour',
    'mini_profile_discrim_colour',
    'task_done_number_colour',
    'task_done_text_colour',
    'task_undone_text_colour',
    'task_undone_number_colour',
    'footer_colour'
]
highlight_colour = "#E84727"


async def get_cards():
    for highlight in highlights:
        card = await TasklistCard.generate_sample(
            skin={highlight: highlight_colour}
        )
        with open('../skins/spec/images/tasklist/{}.png'.format(highlight), 'wb') as image_file:
            image_file.write(card.fp.read())

if __name__ == '__main__':
    asyncio.run(get_cards())
