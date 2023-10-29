import asyncio
import datetime as dt
from src.cards import TasklistCard


highlight = "mini_profile_badge_text_colour"
highlight_colour = "#E84727"

async def get_card():
    card = await TasklistCard.generate_sample(
        skin={highlight: highlight_colour}
    )
    with open('samples/tasklist-sample.png', 'wb') as image_file:
        image_file.write(card.fp.read())

if __name__ == '__main__':
    asyncio.run(get_card())
