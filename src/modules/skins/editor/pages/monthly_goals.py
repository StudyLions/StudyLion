from gui.cards import MonthlyGoalCard

from ... import babel
from ..skinsetting import ColourSetting, SkinSetting, ColoursSetting
from ..layout import Page, SettingGroup

_p = babel._p

"""
mini_profile_name_colour
mini_profile_badge_colour
mini_profile_badge_text_colour
mini_profile_discrim_colour

title_colour
footer_colour

progress_bg_colour
progress_colour
[attendance_rate_colour, task_count_colour, studied_hour_colour]
[attendance_colour, task_done_colour, studied_text_colour, task_goal_colour]
task_goal_number_colour

task_header_colour
task_done_number_colour
task_undone_number_colour
task_done_text_colour
task_undone_text_colour
"""

monthly_goal_page = Page(
    display_name=_p('skinsettings|page:monthly_goal|display_name', "Monthly Goals"),
    editing_description=_p(
        'skinsettings|page:monthly_goal|edit_desc',
        "Options for the monthly goal card."
    ),
    preview_description=None,
    visible_in_preview=True,
    render_card=MonthlyGoalCard
)

title_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='title_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:title_colour|display_name',
        "Title"
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:title_colour|desc',
        ""
    )
)

progress_bg_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='progress_bg_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:progress_bg_colour|display_name',
        "Bar Bg"
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:progress_bg_colour|desc',
        ""
    )
)

progress_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='progress_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:progress_colour|display_name',
        "Bar Fg"
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:progress_colour|desc',
        ""
    )
)

attendance_rate_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='attendance_rate_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:attendance_rate_colour|display_name',
        ""
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:attendance_rate_colour|desc',
        ""
    )
)

attendance_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='attendance_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:attendance_colour|display_name',
        ""
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:attendance_colour|desc',
        ""
    )
)

task_count_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='task_count_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:task_count_colour|display_name',
        ""
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:task_count_colour|desc',
        ""
    )
)

task_done_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='task_done_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:task_done_colour|display_name',
        ""
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:task_done_colour|desc',
        ""
    )
)

task_goal_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='task_goal_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:task_goal_colour|display_name',
        ""
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:task_goal_colour|desc',
        ""
    )
)

task_goal_number_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='task_goal_number_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:task_goal_number_colour|display_name',
        "Task Goal"
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:task_goal_number_colour|desc',
        ""
    )
)

studied_text_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='studied_text_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:studied_text_colour|display_name',
        ""
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:studied_text_colour|desc',
        ""
    )
)

studied_hour_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='studied_hour_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:studied_hour_colour|display_name',
        ""
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:studied_hour_colour|desc',
        ""
    )
)

text_highlight_colour = ColoursSetting(
    attendance_rate_colour,
    task_count_colour,
    studied_hour_colour,
    display_name=_p(
        'skinsettings|page:monthly_goal|set:text_highlight_colour|display_name',
        "Highlight Text"
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:text_highlight_colour|desc',
        "Progress text colour."
    )
)

text_colour = ColoursSetting(
    attendance_colour,
    task_done_colour,
    studied_text_colour,
    task_goal_colour,
    display_name=_p(
        'skinsettings|page:monthly_goal|set:text_colour|display_name',
        "Text"
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:text_colour|desc',
        "Achievement description text colour."
    )
)

task_header_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='task_header_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:task_header_colour|display_name',
        "Task Header"
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:task_header_colour|desc',
        ""
    )
)

task_done_number_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='task_done_number_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:task_done_number_colour|display_name',
        "Checked Number"
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:task_done_number_colour|desc',
        ""
    )
)

task_undone_number_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='task_undone_number_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:task_undone_number_colour|display_name',
        "Unchecked Number"
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:task_undone_number_colour|desc',
        ""
    )
)

task_done_text_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='task_done_text_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:task_done_text_colour|display_name',
        "Checked Text"
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:task_done_text_colour|desc',
        ""
    )
)

task_undone_text_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='task_undone_text_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:task_undone_text_colour|display_name',
        "Unchecked Text"
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:task_undone_text_colour|desc',
        ""
    )
)

footer_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='footer_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:footer_colour|display_name',
        "Footer"
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:footer_colour|desc',
        ""
    )
)


mini_profile_badge_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='mini_profile_badge_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:mini_profile_badge_colour|display_name',
        'Badge Background'
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:mini_profile_badge_colour|desc',
        "Mini-profile badge background colour."
    )
)

mini_profile_badge_text_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='mini_profile_badge_text_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:mini_profile_badge_text_colour|display_name',
        'Badge Text'
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:mini_profile_badge_text_colour|desc',
        ""
    )
)

mini_profile_name_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='mini_profile_name_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:mini_profile_name_colour|display_name',
        'Username'
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:mini_profile_name_colour|desc',
        "Mini-profile username colour."
    )
)

mini_profile_discrim_colour = ColourSetting(
    card=MonthlyGoalCard,
    property_name='mini_profile_discrim_colour',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:mini_profile_discrim_colour|display_name',
        'Discriminator'
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:mini_profile_discrim_colour|desc',
        "Mini-profile discriminator colour."
    )
)


mini_profile_group = SettingGroup(
    _p('skinsettings|page:monthly_goal|grp:mini_profile', "Profile"),
    description=_p(
        'skinsettings|page:monthly_goal|grp:mini_profile|desc',
        "Customise the mini-profile shown above the goals."
    ),
    custom_id='monthlygoal-profile',
    settings=(
        mini_profile_name_colour,
        mini_profile_discrim_colour,
        mini_profile_badge_colour,
        mini_profile_badge_text_colour,
    )
)

misc_group = SettingGroup(
    _p('skinsettings|page:monthly_goal|grp:misc', "Miscellaneous"),
    description=_p(
        'skinsettings|page:monthly_goal|grp:misc|desc',
        "Other miscellaneous colours."
    ),
    custom_id='monthlygoal-misc',
    settings=(
        title_colour,
        footer_colour,
    )
)

task_colour_group = SettingGroup(
    _p('skinsettings|page:monthly_goal|grp:task_colour', "Task colours"),
    description=_p(
        'skinsettings|page:monthly_goal|grp:task_colour|desc',
        "Text and number colours for (in)complete goals."
    ),
    custom_id='monthlygoal-tasks',
    settings=(
        task_undone_number_colour,
        task_done_number_colour,
        task_undone_text_colour,
        task_done_text_colour,
    )
)

progress_colour_group = SettingGroup(
    _p('skinsettings|page:monthly_goal|grp:progress_colour', "Progress Colours"),
    description=_p(
        'skinsettings|page:monthly_goal|grp:progress_colour|desc',
        "Customise colours for the monthly achievement progress."
    ),
    custom_id='monthlygoal-progress',
    settings=(
        progress_bg_colour,
        progress_colour,
        text_colour,
        text_highlight_colour,
        task_goal_number_colour
    )
)

base_skin = SkinSetting(
    card=MonthlyGoalCard,
    property_name='base_skin_id',
    display_name=_p(
        'skinsettings|page:monthly_goal|set:base_skin|display_name',
        'Skin'
    ),
    description=_p(
        'skinsettings|page:monthly_goal|set:base_skin|desc',
        "Select a Skin Preset."
    )
)

base_skin_group = SettingGroup(
    _p('skinsettings|page:monthly_goal|grp:base_skin', "Monthly Goals Skin"),
    description=_p(
        'skinsettings|page:monthly_goal|grp:base_skin|desc',
        "Asset pack and default values for the Monthly Goals."
    ),
    custom_id='monthlygoals-skin',
    settings=(base_skin,),
    ungrouped=True
)

monthly_goal_page.groups = [
    base_skin_group,
    mini_profile_group,
    misc_group,
    progress_colour_group,
    task_colour_group
]

