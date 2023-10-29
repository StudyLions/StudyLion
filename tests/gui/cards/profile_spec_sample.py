import asyncio
import datetime as dt
from src.cards import ProfileCard as _Card


highlights = [
    "header_colour_1",
    "header_colour_2",
    "counter_bg_colour",
    "counter_colour",
    "subheader_colour",
    "badge_text_colour",
    "badge_blob_colour",
    "rank_name_colour",
    "rank_hours_colour",
    "bar_full_colour",
    "bar_empty_colour",
    "next_rank_colour"
]
highlight_colour = "#E84727"
card_name = "profile"


async def get_cards():
    strings = []
    for highlight in highlights:
        card = await _Card.generate_sample(
            skin={highlight: highlight_colour}
        )
        with open(f"../skins/spec/images/{card_name}/{highlight}.png", 'wb') as image_file:
            image_file.write(card.fp.read())

        esc_highlight = highlight.replace('_', '\\_')
        string = f"""
\\hypertarget{{{card_name}-{highlight.replace('_', '-')}}}{{\\texttt{{{esc_highlight}}}}} & &
\\includegraphics[width=.25\\textwidth,valign=m]{{images/{card_name}/{highlight}.png}}
\\\\
        """
        strings.append(string)

    print('\n'.join(strings))

if __name__ == '__main__':
    asyncio.run(get_cards())
