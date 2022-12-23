import asyncio
import datetime as dt
from src.cards import WeeklyStatsCard as _Card


highlights = [
    'title_colour',
    'top_hours_colour',
    'top_hours_bg_colour',
    'top_line_colour',
    'top_weekday_colour',
    'top_date_colour',
    'top_this_colour',
    'top_last_colour',
    'btm_weekly_background_colour',
    'btm_this_colour',
    'btm_last_colour',
    'btm_weekday_colour',
    'btm_day_colour',
    'btm_bar_horiz_colour',
    'btm_bar_vert_colour',
    'this_week_colour',
    'last_week_colour',
    'footer_colour'
]
highlight_colour = "#E84727"
card_name = "weekly"


async def get_cards():
    strings = []
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
