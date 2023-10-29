from gui.cards import ProfileCard

from ... import babel
from ..skinsetting import ColourSetting, SkinSetting, ColoursSetting
from ..layout import Page, SettingGroup

_p = babel._p



profile_page = Page(
    display_name=_p('skinsettings|page:profile|display_name', "Member Profile"),
    editing_description=_p(
        'skinsettings|page:profile|edit_desc',
        "Options for the member profile card."
    ),
    preview_description=None,
    visible_in_preview=True,
    render_card=ProfileCard
)


header_colour_1 = ColourSetting(
    card=ProfileCard,
    property_name='header_colour_1',
    display_name=_p(
        'skinsettings|page:profile|set:header_colour_1|display_name',
        'Username'
    ),
    description=_p(
        'skinsettings|page:profile|set:header_colour_1|desc',
        "Text colour of the profile username."
    )
)

header_colour_2 = ColourSetting(
    card=ProfileCard,
    property_name='header_colour_2',
    display_name=_p(
        'skinsettings|page:profile|set:header_colour_2|display_name',
        'Discriminator'
    ),
    description=_p(
        'skinsettings|page:profile|set:header_colour_2|desc',
        "Text colour of the profile dscriminator."
    )
)

counter_bg_colour = ColourSetting(
    card=ProfileCard,
    property_name='counter_bg_colour',
    display_name=_p(
        'skinsettings|page:profile|set:counter_bg_colour|display_name',
        'Background'
    ),
    description=_p(
        'skinsettings|page:profile|set:counter_bg_colour|desc',
        "Colour of the coin/gem/gift backgrounds."
    )
)

counter_colour = ColourSetting(
    card=ProfileCard,
    property_name='counter_colour',
    display_name=_p(
        'skinsettings|page:profile|set:counter_colour|display_name',
        'Text'
    ),
    description=_p(
        'skinsettings|page:profile|set:counter_colour|desc',
        "Colour of the coin/gem/gift text."
    )
)

subheader_colour = ColourSetting(
    card=ProfileCard,
    property_name='subheader_colour',
    display_name=_p(
        'skinsettings|page:profile|set:subheader_colour|display_name',
        'Column Header'
    ),
    description=_p(
        'skinsettings|page:profile|set:subheader_colour|desc',
        "Colour of the Profile/Achievements header."
    )
)

badge_text_colour = ColourSetting(
    card=ProfileCard,
    property_name='badge_text_colour',
    display_name=_p(
        'skinsettings|page:profile|set:badge_text_colour|display_name',
        'Badge Text'
    ),
    description=_p(
        'skinsettings|page:profile|set:badge_text_colour|desc',
        "Colour of the profile badge text."
    )
)

badge_blob_colour = ColourSetting(
    card=ProfileCard,
    property_name='badge_blob_colour',
    display_name=_p(
        'skinsettings|page:profile|set:badge_blob_colour|display_name',
        'Background'
    ),
    description=_p(
        'skinsettings|page:profile|set:badge_blob_colour|desc',
        "Colour of the profile badge background."
    )
)

rank_name_colour = ColourSetting(
    card=ProfileCard,
    property_name='rank_name_colour',
    display_name=_p(
        'skinsettings|page:profile|set:rank_name_colour|display_name',
        'Current Rank'
    ),
    description=_p(
        'skinsettings|page:profile|set:rank_name_colour|desc',
        "Colour of the current study rank name."
    )
)

rank_hours_colour = ColourSetting(
    card=ProfileCard,
    property_name='rank_hours_colour',
    display_name=_p(
        'skinsettings|page:profile|set:rank_hours_colour|display_name',
        'Required Hours'
    ),
    description=_p(
        'skinsettings|page:profile|set:rank_hours_colour|desc',
        "Colour of the study rank hour range."
    )
)

bar_full_colour = ColourSetting(
    card=ProfileCard,
    property_name='bar_full_colour',
    display_name=_p(
        'skinsettings|page:profile|set:bar_full_colour|display_name',
        'Bar Full'
    ),
    description=_p(
        'skinsettings|page:profile|set:bar_full_colour|desc',
        "Foreground progress bar colour."
    )
)

bar_empty_colour = ColourSetting(
    card=ProfileCard,
    property_name='bar_empty_colour',
    display_name=_p(
        'skinsettings|page:profile|set:bar_empty_colour|display_name',
        'Bar Empty'
    ),
    description=_p(
        'skinsettings|page:profile|set:bar_empty_colour|desc',
        "Background progress bar colour."
    )
)

next_rank_colour = ColourSetting(
    card=ProfileCard,
    property_name='next_rank_colour',
    display_name=_p(
        'skinsettings|page:profile|set:next_rank_colour|display_name',
        'Next Rank'
    ),
    description=_p(
        'skinsettings|page:profile|set:next_rank_colour|desc',
        "Colour of the next rank name and hours."
    )
)

title_colour_group = SettingGroup(
    _p('skinsettings|page:profile|grp:title_colour', "Title Colours"),
    description=_p(
        'skinsettings|page:profile|grp:title_colour|desc',
        "Header and suheader text colours."
    ),
    custom_id='profile-titles',
    settings=(
        header_colour_1,
        header_colour_2,
        subheader_colour
    ),
)

badge_colour_group = SettingGroup(
    _p('skinsettings|page:profile|grp:badge_colour', "Profile Badge Colours"),
    description=_p(
        'skinsettings|page:profile|grp:badge_colour|desc',
        "Text and background for the profile badges."
    ),
    custom_id='profile-badges',
    settings=(
        badge_text_colour,
        badge_blob_colour
    ),
)

counter_colour_group = SettingGroup(
    _p('skinsettings|page:profile|grp:counter_colour', "Counter Colours"),
    description=_p(
        'skinsettings|page:profile|grp:counter_colour|desc',
        "Text and background for the coin/gem/gift counters."
    ),
    custom_id='profile-counters',
    settings=(
        counter_colour,
        counter_bg_colour
    ),
)

rank_colour_group = SettingGroup(
    _p('skinsettings|page:profile|grp:rank_colour', "Progress Bar"),
    description=_p(
        'skinsettings|page:profile|grp:rank_colour|desc',
        "Colours for the study badge/rank progress bar."
    ),
    custom_id='profile-progress',
    settings=(
        rank_name_colour,
        rank_hours_colour,
        next_rank_colour,
        bar_full_colour,
        bar_empty_colour
    ),
)

base_skin = SkinSetting(
    card=ProfileCard,
    property_name='base_skin_id',
    display_name=_p(
        'skinsettings|page:profile|set:base_skin|display_name',
        'Skin'
    ),
    description=_p(
        'skinsettings|page:profile|set:base_skin|desc',
        "Select a Skin Preset."
    )
)

base_skin_group = SettingGroup(
    _p('skinsettings|page:profile|grp:base_skin', "Profile Skin"),
    description=_p(
        'skinsettings|page:profile|grp:base_skin|desc',
        "Asset pack and default values for this card."
    ),
    custom_id='profile-skin',
    settings=(base_skin,),
    ungrouped=True
)

profile_page.groups = [
    base_skin_group,
    title_colour_group,
    badge_colour_group,
    rank_colour_group,
    counter_colour_group,
]

