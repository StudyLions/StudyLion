import asyncio
import random
import datetime as dt
from src.cards import WeeklyGoalCard as _Card


highlights = [
    'title_colour',
    'mini_profile_name_colour',
    'mini_profile_discrim_colour',
    'mini_profile_badge_colour',
    'mini_profile_badge_text_colour',
    'progress_bg_colour',
    'progress_colour',
    'task_count_colour',
    'task_done_colour',
    'task_goal_colour',
    'task_goal_number_colour',
    'attendance_rate_colour',
    'attendance_colour',
    'studied_text_colour',
    'studied_hour_colour',
    'task_header_colour',
    'task_done_number_colour',
    'task_done_text_colour',
    'task_undone_number_colour',
    'task_undone_text_colour',
    'footer_colour'
]
highlight_colour = "#E84727"
card_name = "weeklygoals"


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
