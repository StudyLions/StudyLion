from gui.cards import ProfileCard

from ... import babel
from ..skinsetting import ColourSetting, SkinSetting, ColoursSetting
from ..layout import Page, SettingGroup

from . import stats, profile

_p = babel._p


summary_page = Page(
    display_name=_p('skinsettings|page:summary|display_name', "Setting Summary"),
    editing_description=_p(
        'skinsettings|page:summary|edit_desc',
        "Simple setup for creating a unified interface theme."
    ),
    preview_description=_p(
        'skinsettings|page:summary|preview_desc',
         "Summary of common settings across the entire interface."
    ),
    visible_in_preview=True,
    render_card=ProfileCard
)

name_colours = ColoursSetting(
    profile.header_colour_1,
    display_name=_p(
        'skinsettings|page:summary|set:name_colours|display_name',
        "username colour"
    ),
    description=_p(
        'skinsettings|page:summary|set:name_colours|desc',
        "Author username colour."
    )
)

discrim_colours = ColoursSetting(
    profile.header_colour_2,
    display_name=_p(
        'skinsettings|page:summary|set:discrim_colours|display_name',
        "discrim colour"
    ),
    description=_p(
        'skinsettings|page:summary|set:discrim_colours|desc',
        "Author discriminator colour."
    )
)

subheader_colour = ColoursSetting(
    stats.header_colour,
    profile.subheader_colour,
    display_name=_p(
        'skinsettings|page:summary|set:subheader_colour|display_name',
        "subheadings"
    ),
    description=_p(
        'skinsettings|page:summary|set:subheader_colour|desc',
        "Colour of subheadings and column headings."
    )
)

header_colour_group = SettingGroup(
    _p('skinsettings|page:summary|grp:header_colour', "Title Colours"),
    description=_p(
        'skinsettings|page:summary|grp:header_colour|desc',
        "Title and header text colours."
    ),
    custom_id='shared-titles',
    settings=(
        subheader_colour,
    )
)

profile_colour_group = SettingGroup(
    _p('skinsettings|page:summary|grp:profile_colour', "Profile Colours"),
    description=_p(
        'skinsettings|page:summary|grp:profile_colour|desc',
        "Profile elements shared across various cards."
    ),
    custom_id='shared-profile',
    settings=(
        name_colours,
        discrim_colours
    )
)

summary_page.groups = [header_colour_group, profile_colour_group]

