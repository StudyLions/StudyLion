from gui.cards import StatsCard

from ... import babel
from ..skinsetting import ColourSetting, SkinSetting, ColoursSetting
from ..layout import Page, SettingGroup

_p = babel._p


stats_page = Page(
    display_name=_p('skinsettings|page:stats|display_name', "Statistics"),
    editing_description=_p(
        'skinsettings|page:stats|edit_desc',
        "Options for the member statistics card."
    ),
    preview_description=None,
    visible_in_preview=True,
    render_card=StatsCard
)


header_colour = ColourSetting(
    card=StatsCard,
    property_name='header_colour',
    display_name=_p(
        'skinsettings|page:stats|set:header_colour|display_name',
        'Titles'
    ),
    description=_p(
        'skinsettings|page:stats|set:header_colour|desc',
        "Top header text colour."
    )
)

stats_subheader_colour = ColourSetting(
    card=StatsCard,
    property_name='stats_subheader_colour',
    display_name=_p(
        'skinsettings|page:stats|set:stats_subheader_colour|display_name',
        'Sections'
    ),
    description=_p(
        'skinsettings|page:stats|set:stats_subheader_colour|desc',
        "Text colour of the Statistics section titles."
    )
)

stats_text_colour = ColourSetting(
    card=StatsCard,
    property_name='stats_text_colour',
    display_name=_p(
        'skinsettings|page:stats|set:stats_text_colour|display_name',
        'Statistics'
    ),
    description=_p(
        'skinsettings|page:stats|set:stats_text_colour|desc',
        "Text colour of the Statistics section bodies."
    )
)

col2_date_colour = ColourSetting(
    card=StatsCard,
    property_name='col2_date_colour',
    display_name=_p(
        'skinsettings|page:stats|set:col2_date_colour|display_name',
        'Date'
    ),
    description=_p(
        'skinsettings|page:stats|set:col2_date_colour|desc',
        "Colour of the current month and year."
    )
)

col2_hours_colour = ColourSetting(
    card=StatsCard,
    property_name='col2_hours_colour',
    display_name=_p(
        'skinsettings|page:stats|set:col2_hours_colour|display_name',
        'Hours'
    ),
    description=_p(
        'skinsettings|page:stats|set:col2_hours_colour|desc',
        "Colour of the monthly hour total."
    )
)

text_colour_group = SettingGroup(
    _p('skinsettings|page:stats|grp:text_colour', "Text Colours"),
    description=_p(
        'skinsettings|page:stats|grp:text_colour|desc',
        "Header colours and statistics text colours."
    ),
    custom_id='stats-text',
    settings=(
        header_colour,
        stats_subheader_colour,
        stats_text_colour,
        col2_date_colour,
        col2_hours_colour
    )
)


cal_weekday_colour = ColourSetting(
    card=StatsCard,
    property_name='cal_weekday_colour',
    display_name=_p(
        'skinsettings|page:stats|set:cal_weekday_colour|display_name',
        'Weekdays'
    ),
    description=_p(
        'skinsettings|page:stats|set:cal_weekday_colour|desc',
        "Colour of the week day letters."
    ),
)

cal_number_colour = ColourSetting(
    card=StatsCard,
    property_name='cal_number_colour',
    display_name=_p(
        'skinsettings|page:stats|set:cal_number_colour|display_name',
        'Numbers'
    ),
    description=_p(
        'skinsettings|page:stats|set:cal_number_colour|desc',
        "General calender day colour."
    ),
)

cal_number_end_colour = ColourSetting(
    card=StatsCard,
    property_name='cal_number_end_colour',
    display_name=_p(
        'skinsettings|page:stats|set:cal_number_end_colour|display_name',
        'Streak Ends'
    ),
    description=_p(
        'skinsettings|page:stats|set:cal_number_end_colour|desc',
        "Day colour where streaks start or end."
    ),
)

cal_streak_middle_colour = ColourSetting(
    card=StatsCard,
    property_name='cal_streak_middle_colour',
    display_name=_p(
        'skinsettings|page:stats|set:cal_streak_middle_colour|display_name',
        'Streak BG'
    ),
    description=_p(
        'skinsettings|page:stats|set:cal_streak_middle_colour|desc',
        "Background colour on streak days."
    ),
)

cal_streak_end_colour = ColourSetting(
    card=StatsCard,
    property_name='cal_streak_end_colour',
    display_name=_p(
        'skinsettings|page:stats|set:cal_streak_end_colour|display_name',
        'Streak End BG'
    ),
    description=_p(
        'skinsettings|page:stats|set:cal_streak_end_colour|desc',
        "Background colour where streaks start/end."
    ),
)

calender_colour_group = SettingGroup(
    _p('skinsettings|page:stats|grp:calender_colour', "Calender Colours"),
    description=_p(
        'skinsettings|page:stats|grp:calender_colour|desc',
        "Number and streak colours for the current calender."
    ),
    custom_id='stats-cal',
    settings=(
        cal_weekday_colour,
        cal_number_colour,
        cal_number_end_colour,
        cal_streak_middle_colour,
        cal_streak_end_colour
    )
)


base_skin = SkinSetting(
    card=StatsCard,
    property_name='base_skin_id',
    display_name=_p(
        'skinsettings|page:stats|set:base_skin|display_name',
        'Skin'
    ),
    description=_p(
        'skinsettings|page:stats|set:base_skin|desc',
        "Select a Skin Preset."
    )
)

base_skin_group = SettingGroup(
    _p('skinsettings|page:stats|grp:base_skin', "Statistics Skin"),
    description=_p(
        'skinsettings|page:stats|grp:base_skin|desc',
        "Asset pack and default values for this card."
    ),
    custom_id='stats-skin',
    settings=(base_skin,),
    ungrouped=True
)

stats_page.groups = [base_skin_group, text_colour_group, calender_colour_group]

