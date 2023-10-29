from gui.cards import LeaderboardCard

from ... import babel
from ..skinsetting import ColourSetting, SkinSetting, ColoursSetting
from ..layout import Page, SettingGroup

_p = babel._p

"""
top_position_colour
top_name_colour
top_hours_colour

entry_position_colour
entry_position_highlight_colour
entry_name_colour
entry_hours_colour

header_text_colour
[subheader_name_colour, subheader_value_colour]

entry_bg_colour
entry_bg_highlight_colour
"""

leaderboard_page = Page(
    display_name=_p('skinsettings|page:leaderboard|display_name', "Leaderboard"),
    editing_description=_p(
        'skinsettings|page:leaderboard|edit_desc',
        "Options for the Leaderboard pages."
    ),
    preview_description=None,
    visible_in_preview=True,
    render_card=LeaderboardCard
)

header_text_colour = ColourSetting(
    card=LeaderboardCard,
    property_name='header_text_colour',
    display_name=_p(
        'skinsettings|page:leaderboard|set:header_text_colour|display_name',
        "Header"
    ),
    description=_p(
        'skinsettings|page:leaderboard|set:header_text_colour|desc',
        "Text colour of the leaderboard header."
    )
)

subheader_name_colour = ColourSetting(
    card=LeaderboardCard,
    property_name='subheader_name_colour',
    display_name=_p(
        'skinsettings|page:leaderboard|set:subheader_name_colour|display_name',
        ""
    ),
    description=_p(
        'skinsettings|page:leaderboard|set:subheader_name_colour|desc',
        ""
    )
)

subheader_value_colour = ColourSetting(
    card=LeaderboardCard,
    property_name='subheader_value_colour',
    display_name=_p(
        'skinsettings|page:leaderboard|set:subheader_value_colour|display_name',
        ""
    ),
    description=_p(
        'skinsettings|page:leaderboard|set:subheader_value_colour|desc',
        ""
    )
)

subheader_colour = ColoursSetting(
    subheader_value_colour,
    subheader_name_colour,
    display_name=_p(
        'skinsettings|page:leaderboard|set:subheader_colour|display_name',
        "Sub-Header"
    ),
    description=_p(
        'skinsettings|page:leaderboard|set:subheader_colour|desc',
        "Text colour of the sub-header line."
    )
)

top_position_colour = ColourSetting(
    card=LeaderboardCard,
    property_name='top_position_colour',
    display_name=_p(
        'skinsettings|page:leaderboard|set:top_position_colour|display_name',
        "Position"
    ),
    description=_p(
        'skinsettings|page:leaderboard|set:top_position_colour|desc',
        "Top 3 position colour."
    )
)

top_name_colour = ColourSetting(
    card=LeaderboardCard,
    property_name='top_name_colour',
    display_name=_p(
        'skinsettings|page:leaderboard|set:top_name_colour|display_name',
        "Name"
    ),
    description=_p(
        'skinsettings|page:leaderboard|set:top_name_colour|desc',
        "Top 3 name colour."
    )
)

top_hours_colour = ColourSetting(
    card=LeaderboardCard,
    property_name='top_hours_colour',
    display_name=_p(
        'skinsettings|page:leaderboard|set:top_hours_colour|display_name',
        "Hours"
    ),
    description=_p(
        'skinsettings|page:leaderboard|set:top_hours_colour|desc',
        "Top 3 hours colour."
    )
)

entry_position_colour = ColourSetting(
    card=LeaderboardCard,
    property_name='entry_position_colour',
    display_name=_p(
        'skinsettings|page:leaderboard|set:entry_position_colour|display_name',
        "Position"
    ),
    description=_p(
        'skinsettings|page:leaderboard|set:entry_position_colour|desc',
        "Position text colour."
    )
)

entry_position_highlight_colour = ColourSetting(
    card=LeaderboardCard,
    property_name='entry_position_highlight_colour',
    display_name=_p(
        'skinsettings|page:leaderboard|set:entry_position_highlight_colour|display_name',
        "Position (HL)"
    ),
    description=_p(
        'skinsettings|page:leaderboard|set:entry_position_highlight_colour|desc',
        "Highlighted position colour."
    )
)

entry_name_colour = ColourSetting(
    card=LeaderboardCard,
    property_name='entry_name_colour',
    display_name=_p(
        'skinsettings|page:leaderboard|set:entry_name_colour|display_name',
        "Name"
    ),
    description=_p(
        'skinsettings|page:leaderboard|set:entry_name_colour|desc',
        "Entry name colour."
    )
)

entry_hours_colour = ColourSetting(
    card=LeaderboardCard,
    property_name='entry_hours_colour',
    display_name=_p(
        'skinsettings|page:leaderboard|set:entry_hours_colour|display_name',
        "Hours"
    ),
    description=_p(
        'skinsettings|page:leaderboard|set:entry_hours_colour|desc',
        "Entry hours colour."
    )
)

entry_bg_colour = ColourSetting(
    card=LeaderboardCard,
    property_name='entry_bg_colour',
    display_name=_p(
        'skinsettings|page:leaderboard|set:entry_bg_colour|display_name',
        "Regular"
    ),
    description=_p(
        'skinsettings|page:leaderboard|set:entry_bg_colour|desc',
        "Background colour of regular entries."
    )
)

entry_bg_highlight_colour = ColourSetting(
    card=LeaderboardCard,
    property_name='entry_bg_highlight_colour',
    display_name=_p(
        'skinsettings|page:leaderboard|set:entry_bg_highlight_colour|display_name',
        "Highlighted"
    ),
    description=_p(
        'skinsettings|page:leaderboard|set:entry_bg_highlight_colour|desc',
        "Background colour of highlighted entries."
    )
)


top_colour_group = SettingGroup(
    _p('skinsettings|page:leaderboard|grp:top_colour', "Top 3"),
    description=_p(
        'skinsettings|page:leaderboard|grp:top_colour|desc',
        "Customise the text colours for the top 3 positions."
    ),
    custom_id='leaderboard-top',
    settings=(
        top_position_colour,
        top_name_colour,
        top_hours_colour
    )
)

entry_text_group = SettingGroup(
    _p('skinsettings|page:leaderboard|grp:entry_text', "Entry Text"),
    description=_p(
        'skinsettings|page:leaderboard|grp:entry_text|desc',
        "Text colours of the leaderboard entries."
    ),
    custom_id='leaderboard-text',
    settings=(
        entry_position_colour,
        entry_position_highlight_colour,
        entry_name_colour,
        entry_hours_colour
    )
)

entry_bg_group = SettingGroup(
    _p('skinsettings|page:leaderboard|grp:entry_bg', "Entry Background"),
    description=_p(
        'skinsettings|page:leaderboard|grp:entry_bg|desc',
        "Background colours of the leaderboard entries."
    ),
    custom_id='leaderboard-bg',
    settings=(
        entry_bg_colour,
        entry_bg_highlight_colour
    )
)

misc_group = SettingGroup(
    _p('skinsettings|page:leaderboard|grp:misc', "Miscellaneous"),
    description=_p(
        'skinsettings|page:leaderboard|grp:misc|desc',
        "Other miscellaneous colour settings."
    ),
    custom_id='leaderboard-misc',
    settings=(
        header_text_colour,
        subheader_colour
    )
)


base_skin = SkinSetting(
    card=LeaderboardCard,
    property_name='base_skin_id',
    display_name=_p(
        'skinsettings|page:leaderboard|set:base_skin|display_name',
        'Skin'
    ),
    description=_p(
        'skinsettings|page:leaderboard|set:base_skin|desc',
        "Select a Skin Preset."
    )
)

base_skin_group = SettingGroup(
    _p('skinsettings|page:leaderboard|grp:base_skin', "Leaderboard Skin"),
    description=_p(
        'skinsettings|page:leaderboard|grp:base_skin|desc',
        "Asset pack and default values for the Leaderboard."
    ),
    custom_id='leaderboard-skin',
    settings=(base_skin,),
    ungrouped=True
)

leaderboard_page.groups = [
    base_skin_group,
    top_colour_group,
    entry_text_group,
    entry_bg_group,
    misc_group
]

