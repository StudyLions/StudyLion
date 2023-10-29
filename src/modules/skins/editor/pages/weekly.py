from gui.cards import WeeklyStatsCard

from ... import babel
from ..skinsetting import ColourSetting, SkinSetting, ColoursSetting
from ..layout import Page, SettingGroup

_p = babel._p


weekly_page = Page(
    display_name=_p('skinsettings|page:weekly|display_name', "Weekly Statistics"),
    editing_description=_p(
        'skinsettings|page:weekly|edit_desc',
        "Options for the weekly statistis card."
    ),
    preview_description=None,
    visible_in_preview=True,
    render_card=WeeklyStatsCard
)

title_colour = ColourSetting(
    card=WeeklyStatsCard,
    property_name='title_colour',
    display_name=_p(
        'skinsettings|page:weekly|set:title_colour|display_name',
        'Title'
    ),
    description=_p(
        'skinsettings|page:weekly|set:title_colour|desc',
        "Colour of the card title."
    )
)
top_hours_colour = ColourSetting(
    card=WeeklyStatsCard,
    property_name='top_hours_colour',
    display_name=_p(
        'skinsettings|page:weekly|set:top_hours_colour|display_name',
        'Hours'
    ),
    description=_p(
        'skinsettings|page:weekly|set:top_hours_colour|desc',
        "Hours axis labels."
    )
)
top_hours_bg_colour = ColourSetting(
    card=WeeklyStatsCard,
    property_name='top_hours_bg_colour',
    display_name=_p(
        'skinsettings|page:weekly|set:top_hours_bg_colour|display_name',
        'Hour Bg'
    ),
    description=_p(
        'skinsettings|page:weekly|set:top_hours_bg_colour|desc',
        "Hours axis label background."
    )
)
top_line_colour = ColourSetting(
    card=WeeklyStatsCard,
    property_name='top_line_colour',
    display_name=_p(
        'skinsettings|page:weekly|set:top_line_colour|display_name',
        'Lines'
    ),
    description=_p(
        'skinsettings|page:weekly|set:top_line_colour|desc',
        "Horizontal graph lines."
    )
)
top_weekday_colour = ColourSetting(
    card=WeeklyStatsCard,
    property_name='top_weekday_colour',
    display_name=_p(
        'skinsettings|page:weekly|set:top_weekday_colour|display_name',
        'Weekdays'
    ),
    description=_p(
        'skinsettings|page:weekly|set:top_weekday_colour|desc',
        "Weekday axis labels."
    )
)
top_date_colour = ColourSetting(
    card=WeeklyStatsCard,
    property_name='top_date_colour',
    display_name=_p(
        'skinsettings|page:weekly|set:top_date_colour|display_name',
        'Dates'
    ),
    description=_p(
        'skinsettings|page:weekly|set:top_date_colour|desc',
        "Weekday date axis labels."
    )
)
top_this_colour = ColourSetting(
    card=WeeklyStatsCard,
    property_name='top_this_colour',
    display_name=_p(
        'skinsettings|page:weekly|set:top_this_colour|display_name',
        'This Week'
    ),
    description=_p(
        'skinsettings|page:weekly|set:top_this_colour|desc',
        "This week bar fill colour."
    )
)
top_last_colour = ColourSetting(
    card=WeeklyStatsCard,
    property_name='top_last_colour',
    display_name=_p(
        'skinsettings|page:weekly|set:top_last_colour|display_name',
        'Last Week'
    ),
    description=_p(
        'skinsettings|page:weekly|set:top_last_colour|desc',
        "Last week bar fill colour."
    )
)
btm_weekday_colour = ColourSetting(
    card=WeeklyStatsCard,
    property_name='btm_weekday_colour',
    display_name=_p(
        'skinsettings|page:weekly|set:btm_weekday_colour|display_name',
        'Weekdays'
    ),
    description=_p(
        'skinsettings|page:weekly|set:btm_weekday_colour|desc',
        "Weekday axis labels."
    )
)
btm_weekly_background_colour = ColourSetting(
    card=WeeklyStatsCard,
    property_name='btm_weekly_background_colour',
    display_name=_p(
        'skinsettings|page:weekly|set:btm_weekly_background_colour|display_name',
        'Weekday Bg'
    ),
    description=_p(
        'skinsettings|page:weekly|set:btm_weekly_background_colour|desc',
        "Weekday axis background."
    )
)
btm_bar_horiz_colour = ColourSetting(
    card=WeeklyStatsCard,
    property_name='btm_bar_horiz_colour',
    display_name=_p(
        'skinsettings|page:weekly|set:btm_bar_horiz_colour|display_name',
        'Bars (Horiz)'
    ),
    description=_p(
        'skinsettings|page:weekly|set:btm_bar_horiz_colour|desc',
        "Horizontal graph bars."
    )
)
btm_bar_vert_colour = ColourSetting(
    card=WeeklyStatsCard,
    property_name='btm_bar_vert_colour',
    display_name=_p(
        'skinsettings|page:weekly|set:btm_bar_vert_colour|display_name',
        'Bars (Vertical)'
    ),
    description=_p(
        'skinsettings|page:weekly|set:btm_bar_vert_colour|desc',
        "Vertical graph bars."
    )
)
btm_this_colour = ColourSetting(
    card=WeeklyStatsCard,
    property_name='btm_this_colour',
    display_name=_p(
        'skinsettings|page:weekly|set:btm_this_colour|display_name',
        'This Week'
    ),
    description=_p(
        'skinsettings|page:weekly|set:btm_this_colour|desc',
        "This week bar fill colour."
    )
)
btm_last_colour = ColourSetting(
    card=WeeklyStatsCard,
    property_name='btm_last_colour',
    display_name=_p(
        'skinsettings|page:weekly|set:btm_last_colour|display_name',
        'Last Week'
    ),
    description=_p(
        'skinsettings|page:weekly|set:btm_last_colour|desc',
        "Last week bar fill colour."
    )
)
btm_day_colour = ColourSetting(
    card=WeeklyStatsCard,
    property_name='btm_day_colour',
    display_name=_p(
        'skinsettings|page:weekly|set:btm_day_colour|display_name',
        'Hours'
    ),
    description=_p(
        'skinsettings|page:weekly|set:btm_day_colour|desc',
        "Hour axis labels."
    )
)
this_week_colour = ColourSetting(
    card=WeeklyStatsCard,
    property_name='this_week_colour',
    display_name=_p(
        'skinsettings|page:weekly|set:this_week_colour|display_name',
        'This Week Legend'
    ),
    description=_p(
        'skinsettings|page:weekly|set:this_week_colour|desc',
        "This week legend text."
    )
)
last_week_colour = ColourSetting(
    card=WeeklyStatsCard,
    property_name='last_week_colour',
    display_name=_p(
        'skinsettings|page:weekly|set:last_week_colour|display_name',
        'Last Week Legend'
    ),
    description=_p(
        'skinsettings|page:weekly|set:last_week_colour|desc',
        "Last week legend text."
    )
)
legend_colour = ColoursSetting(
    this_week_colour,
    last_week_colour,
    display_name=_p(
        'skinsettings|page:weekly|set:legend_colour|display_name',
        'Legend'
    ),
    description=_p(
        'skinsettings|page:weekly|set:legend_colour|desc',
        "Legend text colour."
    )
)
footer_colour = ColourSetting(
    card=WeeklyStatsCard,
    property_name='footer_colour',
    display_name=_p(
        'skinsettings|page:weekly|set:footer_colour|display_name',
        'Footer'
    ),
    description=_p(
        'skinsettings|page:weekly|set:footer_colour|desc',
        "Footer text colour."
    )
)

base_skin = SkinSetting(
    card=WeeklyStatsCard,
    property_name='base_skin_id',
    display_name=_p(
        'skinsettings|page:weekly|set:base_skin|display_name',
        'Skin'
    ),
    description=_p(
        'skinsettings|page:weekly|set:base_skin|desc',
        "Select a Skin Preset."
    )
)

base_skin_group = SettingGroup(
    _p('skinsettings|page:weekly|grp:base_skin', "Weekly Stats Skin"),
    description=_p(
        'skinsettings|page:weekly|grp:base_skin|desc',
        "Asset pack and default values for this card."
    ),
    custom_id='weekly-skin',
    settings=(base_skin,),
    ungrouped=True
)

top_colour_group = SettingGroup(
    _p('skinsettings|page:weekly|grp:top_colour', "Top Graph"),
    description=_p(
        'skinsettings|page:weekly|grp:top_colour|desc',
        "Customise the top graph colourscheme."
    ),
    custom_id='weekly-top',
    settings=(
        top_hours_colour,
        top_weekday_colour,
        top_date_colour,
        top_this_colour,
        top_last_colour,
    )
)

bottom_colour_group = SettingGroup(
    _p('skinsettings|page:weekly|grp:bottom_colour', "Bottom Graph"),
    description=_p(
        'skinsettings|page:weekly|grp:bottom_colour|desc',
        "Customise the bottom graph colourscheme."
    ),
    custom_id='weekly-bottom',
    settings=(
        btm_weekday_colour,
        btm_day_colour,
        btm_this_colour,
        btm_last_colour,
        btm_bar_horiz_colour,
    )
)

misc_group = SettingGroup(
    _p('skinsettings|page:weekly|grp:misc', "Misc Colours"),
    description=_p(
        'skinsettings|page:weekly|grp:misc|desc',
        "Miscellaneous card colours."
    ),
    custom_id='weekly-misc',
    settings=(
        title_colour,
        legend_colour,
        footer_colour,
    )
)

base_skin = SkinSetting(
    card=WeeklyStatsCard,
    property_name='base_skin_id',
    display_name=_p(
        'skinsettings|page:weekly|set:base_skin|display_name',
        'Skin'
    ),
    description=_p(
        'skinsettings|page:weekly|set:base_skin|desc',
        "Select a Skin Preset."
    )
)

base_skin_group = SettingGroup(
    _p('skinsettings|page:weekly|grp:base_skin', "Weekly Stats Skin"),
    description=_p(
        'skinsettings|page:weekly|grp:base_skin|desc',
        "Asset pack and default values for the Weekly Statistics."
    ),
    custom_id='weekly-skin',
    settings=(base_skin,),
    ungrouped=True
)

weekly_page.groups = [
    base_skin_group,
    top_colour_group,
    bottom_colour_group,
    misc_group,
]

