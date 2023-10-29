from gui.cards import MonthlyStatsCard

from ... import babel
from ..skinsetting import ColourSetting, SkinSetting, ColoursSetting
from ..layout import Page, SettingGroup

_p = babel._p

""""
title_colour
[this_month_colour, last_month_colour]
[stats_key_colour, stats_value_colour]
footer_colour

top_hours_colour
top_hours_bg_colour
top_date_colour
top_line_colour

top_this_colour
top_this_hours_colour
top_last_colour
top_last_hours_colour

weekday_background_colour
weekday_colour
month_background_colour
month_colour
"""

monthly_page = Page(
    display_name=_p('skinsettings|page:monthly|display_name', "Monthly Statistics"),
    editing_description=_p(
        'skinsettings|page:monthly|edit_desc',
        "Options for the monthly statistis card."
    ),
    preview_description=None,
    visible_in_preview=True,
    render_card=MonthlyStatsCard
)


title_colour = ColourSetting(
    card=MonthlyStatsCard,
    property_name='title_colour',
    display_name=_p(
        'skinsettings|page:monthly|set:title_colour|display_name',
        'Title'
    ),
    description=_p(
        'skinsettings|page:monthly|set:title_colour|desc',
        "Colour of the card title."
    )
)
top_hours_colour = ColourSetting(
    card=MonthlyStatsCard,
    property_name='top_hours_colour',
    display_name=_p(
        'skinsettings|page:monthly|set:top_hours_colour|display_name',
        'Hours'
    ),
    description=_p(
        'skinsettings|page:monthly|set:top_hours_colour|desc',
        "Hour axis labels."
    )
)
top_hours_bg_colour = ColourSetting(
    card=MonthlyStatsCard,
    property_name='top_hours_bg_colour',
    display_name=_p(
        'skinsettings|page:monthly|set:top_hours_bg_colour|display_name',
        'Hours Bg'
    ),
    description=_p(
        'skinsettings|page:monthly|set:top_hours_bg_colour|desc',
        "Hour axis label background."
    )
)
top_line_colour = ColourSetting(
    card=MonthlyStatsCard,
    property_name='top_line_colour',
    display_name=_p(
        'skinsettings|page:monthly|set:top_line_colour|display_name',
        'Lines'
    ),
    description=_p(
        'skinsettings|page:monthly|set:top_line_colour|desc',
        "Horizontal graph lines."
    )
)
top_date_colour = ColourSetting(
    card=MonthlyStatsCard,
    property_name='top_date_colour',
    display_name=_p(
        'skinsettings|page:monthly|set:top_date_colour|display_name',
        'Days'
    ),
    description=_p(
        'skinsettings|page:monthly|set:top_date_colour|desc',
        "Day axis labels."
    )
)
top_this_colour = ColourSetting(
    card=MonthlyStatsCard,
    property_name='top_this_colour',
    display_name=_p(
        'skinsettings|page:monthly|set:top_this_colour|display_name',
        'This Month Bar'
    ),
    description=_p(
        'skinsettings|page:monthly|set:top_this_colour|desc',
        "This month bar fill colour."
    )
)
top_last_colour = ColourSetting(
    card=MonthlyStatsCard,
    property_name='top_last_colour',
    display_name=_p(
        'skinsettings|page:monthly|set:top_last_colour|display_name',
        'Last Month Bar'
    ),
    description=_p(
        'skinsettings|page:monthly|set:top_last_colour|desc',
        "Last month bar fill colour."
    )
)
top_this_hours_colour = ColourSetting(
    card=MonthlyStatsCard,
    property_name='top_this_hours_colour',
    display_name=_p(
        'skinsettings|page:monthly|set:top_this_hours_colour|display_name',
        'This Month Hours'
    ),
    description=_p(
        'skinsettings|page:monthly|set:top_this_hours_colour|desc',
        "This month hour text."
    )
)
top_last_hours_colour = ColourSetting(
    card=MonthlyStatsCard,
    property_name='top_last_hours_colour',
    display_name=_p(
        'skinsettings|page:monthly|set:top_last_hours_colour|display_name',
        'Last Month Hours'
    ),
    description=_p(
        'skinsettings|page:monthly|set:top_last_hours_colour|desc',
        "Last month hour text."
    )
)
this_month_colour = ColourSetting(
    card=MonthlyStatsCard,
    property_name='this_month_colour',
    display_name=_p(
        'skinsettings|page:monthly|set:this_month_colour|display_name',
        'This Month Legend'
    ),
    description=_p(
        'skinsettings|page:monthly|set:this_month_colour|desc',
        "This month legend text."
    )
)
last_month_colour = ColourSetting(
    card=MonthlyStatsCard,
    property_name='last_month_colour',
    display_name=_p(
        'skinsettings|page:monthly|set:last_month_colour|display_name',
        'Last Month Legend'
    ),
    description=_p(
        'skinsettings|page:monthly|set:last_month_colour|desc',
        "Last month legend text."
    )
)
legend_colour = ColoursSetting(
    this_month_colour,
    last_month_colour,
    display_name=_p(
        'skinsettings|page:monthly|set:legend_colour|display_name',
        'Legend'
    ),
    description=_p(
        'skinsettings|page:monthly|set:legend_colour|desc',
        "Legend text colour."
    )
)

weekday_background_colour = ColourSetting(
    card=MonthlyStatsCard,
    property_name='weekday_background_colour',
    display_name=_p(
        'skinsettings|page:monthly|set:weekday_background_colour|display_name',
        'Weekday Bg'
    ),
    description=_p(
        'skinsettings|page:monthly|set:weekday_background_colour|desc',
        "Weekday axis background colour."
    )
)
weekday_colour = ColourSetting(
    card=MonthlyStatsCard,
    property_name='weekday_colour',
    display_name=_p(
        'skinsettings|page:monthly|set:weekday_colour|display_name',
        'Weekdays'
    ),
    description=_p(
        'skinsettings|page:monthly|set:weekday_colour|desc',
        "Weekday axis labels."
    )
)
month_background_colour = ColourSetting(
    card=MonthlyStatsCard,
    property_name='month_background_colour',
    display_name=_p(
        'skinsettings|page:monthly|set:month_background_colour|display_name',
        'Month Bg'
    ),
    description=_p(
        'skinsettings|page:monthly|set:month_background_colour|desc',
        "Month axis label backgrounds."
    )
)
month_colour = ColourSetting(
    card=MonthlyStatsCard,
    property_name='month_colour',
    display_name=_p(
        'skinsettings|page:monthly|set:month_colour|display_name',
        'Months'
    ),
    description=_p(
        'skinsettings|page:monthly|set:month_colour|desc',
        "Month axis label text."
    )
)
stats_key_colour = ColourSetting(
    card=MonthlyStatsCard,
    property_name='stats_key_colour',
    display_name=_p(
        'skinsettings|page:monthly|set:stats_key_colour|display_name',
        'Stat Names'
    ),
    description=_p(
        'skinsettings|page:monthly|set:stats_key_colour|desc',
        ""
    )
)
stats_value_colour = ColourSetting(
    card=MonthlyStatsCard,
    property_name='stats_value_colour',
    display_name=_p(
        'skinsettings|page:monthly|set:stats_value_colour|display_name',
        'Stat Values'
    ),
    description=_p(
        'skinsettings|page:monthly|set:stats_value_colour|desc',
        ""
    )
)
statistics_colour = ColoursSetting(
    stats_key_colour,
    stats_value_colour,
    display_name=_p(
        'skinsettings|page:monthly|set:statistics_colour|display_name',
        'Statistics'
    ),
    description=_p(
        'skinsettings|page:monthly|set:statistics_colour|desc',
        "Summary Statistics"
    )
)
footer_colour = ColourSetting(
    card=MonthlyStatsCard,
    property_name='footer_colour',
    display_name=_p(
        'skinsettings|page:monthly|set:footer_colour|display_name',
        'Footer'
    ),
    description=_p(
        'skinsettings|page:monthly|set:footer_colour|desc',
        "Footer text colour."
    )
)

top_graph_group = SettingGroup(
    _p('skinsettings|page:monthly|grp:top_graph', "Top Graph"),
    description=_p(
        'skinsettings|page:monthly|grp:top_graph|desc',
        "Customise the axis and style of the top graph."
    ),
    custom_id='monthly-top',
    settings=(
        top_hours_colour,
        top_hours_bg_colour,
        top_date_colour,
        top_line_colour
    )
)

top_hours_group = SettingGroup(
    _p('skinsettings|page:monthly|grp:top_hours', "Hours"),
    description=_p(
        'skinsettings|page:monthly|grp:top_hours|desc',
        "Customise the colour of this week and last week."
    ),
    custom_id='monthly-hours',
    settings=(
        top_this_colour,
        top_this_hours_colour,
        top_last_colour,
        top_last_hours_colour
    )
)

bottom_graph_group = SettingGroup(
    _p('skinsettings|page:monthly|grp:bottom_graph', "Heatmap"),
    description=_p(
        'skinsettings|page:monthly|grp:bottom_graph|desc',
        "Customise the axis and style of the heatmap."
    ),
    custom_id='monthly-heatmap',
    settings=(
        weekday_background_colour,
        weekday_colour,
        month_background_colour,
        month_colour
    )
)

misc_group = SettingGroup(
    _p('skinsettings|page:monthly|grp:misc', "Miscellaneous"),
    description=_p(
        'skinsettings|page:monthly|grp:misc|desc',
        "Miscellaneous colour options."
    ),
    custom_id='monthly-misc',
    settings=(
        title_colour,
        legend_colour,
        statistics_colour,
        footer_colour
    )
)

base_skin = SkinSetting(
    card=MonthlyStatsCard,
    property_name='base_skin_id',
    display_name=_p(
        'skinsettings|page:monthly|set:base_skin|display_name',
        'Skin'
    ),
    description=_p(
        'skinsettings|page:monthly|set:base_skin|desc',
        "Select a Skin Preset."
    )
)

base_skin_group = SettingGroup(
    _p('skinsettings|page:monthly|grp:base_skin', "Monthly Stats Skin"),
    description=_p(
        'skinsettings|page:monthly|grp:base_skin|desc',
        "Asset pack and default values for the Monthly Statistics."
    ),
    custom_id='monthly-skin',
    settings=(base_skin,),
    ungrouped=True
)

monthly_page.groups = [
    base_skin_group,
    top_graph_group,
    top_hours_group,
    bottom_graph_group,
    misc_group
]

