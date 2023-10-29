import asyncio
import random
import datetime as dt
from src.cards import LeaderboardCard as _Card


highlights = [
    "header_text_colour",
    "subheader_name_colour",
    "subheader_value_colour",
    "top_position_colour",
    "top_name_colour",
    "top_hours_colour",
    "entry_position_colour",
    "entry_position_highlight_colour",
    "entry_name_colour",
    "entry_hours_colour",
    "entry_bg_colour",
    "entry_bg_highlight_colour"
]
highlight_colour = "#E84727"
card_name = "leaderboard"


async def get_cards():
    strings = []
    random.seed(0)
    for highlight in highlights:
        card = await _Card.generate_sample(
            skin={highlight: highlight_colour}
        )
        with open(f"../skins/spec/images/{card_name}/{highlight}.png", 'wb') as image_file:
            image_file.write(card.fp.read())

        esc_highlight = highlight.replace('_', '\\_')
        string = f"""\
\\hypertarget{{{card_name}-{highlight.replace('_', '-')}}}{{\\texttt{{{esc_highlight}}}}} & &
\\includegraphics[width=.25\\textwidth,valign=m]{{images/{card_name}/{highlight}.png}}
\\\\"""
        strings.append(string)

    print('\n'.join(strings))

if __name__ == '__main__':
    asyncio.run(get_cards())
