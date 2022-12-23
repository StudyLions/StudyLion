import asyncio
import random
import datetime as dt
from src.cards import MonthlyStatsCard as _Card


highlights = [
    'title_colour',
    'top_hours_colour',
    'top_hours_bg_colour',
    'top_line_colour',
    'top_date_colour',
    'top_this_colour',
    'top_last_colour',
    'top_this_hours_colour',
    'top_last_hours_colour',
    'this_month_colour',
    'last_month_colour',
    'heatmap_empty_colour',
    'weekday_background_colour',
    'weekday_colour',
    'month_background_colour',
    'month_colour',
    'stats_key_colour',
    'stats_value_colour',
    'footer_colour',
]
highlight_colour = "#E84727"
card_name = "monthly"

highlights = ['heatmap_colours']
highlight_colour = ["#E84727"]

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
