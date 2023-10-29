from typing import Optional
import asyncio
import copy
import json
import datetime as dt
from io import StringIO

import discord
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.select import select, Select, SelectOption
from discord.ui.text_input import TextInput, TextStyle

from meta import conf, LionBot
from meta.errors import UserInputError, ResponseTimedOut

from ..lib import MessageArgs, utc_now

from . import MessageUI, util_babel, error_handler_for, FastModal, ModalRetryUI, Confirm, AsComponents, AButton


_p = util_babel._p


class MsgEditorInput(FastModal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @error_handler_for(UserInputError)
    async def rerequest(self, interaction, error):
        await ModalRetryUI(self, error.msg).respond_to(interaction)


class MsgEditor(MessageUI):
    def __init__(self, bot: LionBot, initial_data: dict, formatter=None, callback=None, **kwargs):
        self.bot = bot
        self.history = [initial_data]  # Last item in history is current state
        self.future = []  # Last item in future is next state

        self._formatter = formatter
        self._callback = callback

        super().__init__(**kwargs)

    @property
    def data(self):
        return self.history[-1]

    # ----- API -----
    async def format_data(self, data):
        """
        Format a MessageData dict for rendering.

        May be extended or overridden for custom formatting.
        By default, uses the provided `formatter` callback (if provided).
        """
        if self._formatter is not None:
            await self._formatter(data)

    def copy_data(self):
        return copy.deepcopy(self.history[-1])

    async def save(self):
        ...

    async def push_change(self, new_data):
        # Cleanup the data
        if (embed_data := new_data.get('embed', None)) is not None and not embed_data:
            new_data.pop('embed')

        t = self.bot.translator.t
        if 'embed' not in new_data and not new_data.get('content', None):
            raise UserInputError(
                t(_p(
                    'ui:msg_editor|error:empty',
                    "Rendering failed! The message content and embed cannot both be empty."
                ))
            )

        if 'embed' in new_data:
            try:
                discord.Embed.from_dict(new_data['embed'])
            except Exception as e:
                raise UserInputError(
                    t(_p(
                        'ui:msg_editor|error:embed_failed',
                        "Rendering failed! Could not parse the embed.\n"
                        "Error: {error}"
                    )).format(error=str(e))
                )

        # Push the state and try displaying it
        self.history.append(new_data)
        old_future = self.future
        self.future = []
        try:
            await self.refresh()
        except discord.HTTPException as e:
            # State failed, rollback and error
            self.history.pop()
            self.future = old_future
            raise UserInputError(
                t(_p(
                    'ui:msg_editor|error:invalid_change',
                    "Rendering failed! The message was not modified.\n"
                    "Error: `{text}`"
                )).format(text=e.text)
            )

    # ----- UI Components -----

    # -- Content Only mode --
    @button(label="EDIT_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def edit_button(self, press: discord.Interaction, pressed: Button):
        """
        Open an editor for the message content
        """
        data = self.copy_data()

        t = self.bot.translator.t
        content_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:content|field:content|label',
                "Message Content"
            )),
            style=TextStyle.long,
            required=False,
            default=data.get('content', ""),
            max_length=2000
        )
        modal = MsgEditorInput(
            content_field,
            title=t(_p('ui:msg_editor|modal:content|title', "Content Editor"))
        )

        @modal.submit_callback()
        async def content_modal_callback(interaction: discord.Interaction):
            new_content = content_field.value
            data['content'] = new_content
            await self.push_change(data)

            await interaction.response.defer()

        await press.response.send_modal(modal)

    async def edit_button_refresh(self):
        t = self.bot.translator.t
        button = self.edit_button
        button.label = t(_p(
            'ui:msg_editor|button:edit|label',
            "Edit Content"
        ))

    @button(label="ADD_EMBED_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def add_embed_button(self, press: discord.Interaction, pressed: Button):
        """
        Attach an embed with some simple fields filled.
        """
        await press.response.defer()
        t = self.bot.translator.t

        sample_embed = {
            "title": t(_p('ui:msg_editor|button:add_embed|sample_embed|title', "Title Placeholder")),
            "description": t(_p('ui:msg_editor|button:add_embed|sample_embed|description', "Description Placeholder")),
        }
        data = self.copy_data()
        data['embed'] = sample_embed
        await self.push_change(data)

    async def add_embed_button_refresh(self):
        t = self.bot.translator.t
        button = self.add_embed_button
        button.label = t(_p(
            'ui:msg_editor|button:add_embed|label',
            "Add Embed"
        ))

    @button(label="RM_EMBED_BUTTON_PLACEHOLDER", style=ButtonStyle.red)
    async def rm_embed_button(self, press: discord.Interaction, pressed: Button):
        """
        Remove the existing embed from the message.
        """
        await press.response.defer()
        t = self.bot.translator.t
        data = self.copy_data()
        data.pop('embed', None)
        data.pop('embeds', None)
        if not data.get('content', '').strip():
            data['content'] = t(_p(
                'ui:msg_editor|button:rm_embed|sample_content',
                "Content Placeholder"
            ))
        await self.push_change(data)

    async def rm_embed_button_refresh(self):
        t = self.bot.translator.t
        button = self.rm_embed_button
        button.label = t(_p(
            'ui:msg_editor|button:rm_embed|label',
            "Remove Embed"
        ))

    # -- Embed Mode --

    @button(label="BODY_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def body_button(self, press: discord.Interaction, pressed: Button):
        """
        Edit the Content, Description, Title, and Colour
        """
        data = self.copy_data()
        embed_data = data.get('embed', {})

        t = self.bot.translator.t

        content_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:body|field:content|label',
                "Message Content"
            )),
            style=TextStyle.long,
            required=False,
            default=data.get('content', ""),
            max_length=2000
        )

        desc_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:body|field:desc|label',
                "Embed Description"
            )),
            style=TextStyle.long,
            required=False,
            default=embed_data.get('description', ""),
            max_length=4000
        )

        title_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:body|field:title|label',
                "Embed Title"
            )),
            style=TextStyle.short,
            required=False,
            default=embed_data.get('title', ""),
            max_length=256
        )

        colour_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:body|field:colour|label',
                "Embed Colour"
            )),
            style=TextStyle.short,
            required=False,
            default=str(discord.Colour(value=embed_data['color'])) if 'color' in embed_data else '',
            placeholder=str(discord.Colour.orange()),
            max_length=7,
            min_length=7
        )

        modal = MsgEditorInput(
            content_field,
            title_field,
            desc_field,
            colour_field,
            title=t(_p('ui:msg_editor|modal:body|title', "Message Body Editor"))
        )

        @modal.submit_callback()
        async def body_modal_callback(interaction: discord.Interaction):
            data['content'] = content_field.value

            if desc_field.value:
                embed_data['description'] = desc_field.value
            else:
                embed_data.pop('description', None)

            if title_field.value:
                embed_data['title'] = title_field.value
            else:
                embed_data.pop('title', None)

            if colour_field.value:
                colourstr = colour_field.value
                try:
                    colour = discord.Colour.from_str(colourstr)
                except ValueError:
                    raise UserInputError(
                        t(_p(
                            'ui:msg_editor|button:body|error:invalid_colour',
                            "Invalid colour format! Please enter colours as hex codes, e.g. `#E67E22`"
                        ))
                    )
                embed_data['color'] = colour.value
            else:
                embed_data.pop('color', None)

            data['embed'] = embed_data

            await self.push_change(data)

            await interaction.response.defer()

        await press.response.send_modal(modal)

    async def body_button_refresh(self):
        t = self.bot.translator.t
        button = self.body_button
        button.label = t(_p(
            'ui:msg_editor|button:body|label',
            "Body"
        ))

    @button(label="AUTHOR_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def author_button(self, press: discord.Interaction, pressed: Button):
        """
        Edit the embed author (author name/link/image url)
        """
        data = self.copy_data()
        embed_data = data.get('embed', {})
        author_data = embed_data.get('author', {})

        t = self.bot.translator.t

        name_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:author|field:name|label',
                "Author Name"
            )),
            style=TextStyle.short,
            required=False,
            default=author_data.get('name', ''),
            max_length=256
        )

        link_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:author|field:link|label',
                "Author URL"
            )),
            style=TextStyle.short,
            required=False,
            default=author_data.get('url', ''),
        )

        image_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:author|field:image|label',
                "Author Image URL"
            )),
            style=TextStyle.short,
            required=False,
            default=author_data.get('icon_url', ''),
        )

        modal = MsgEditorInput(
            name_field,
            link_field,
            image_field,
            title=t(_p('ui:msg_editor|modal:author|title', "Embed Author Editor"))
        )

        @modal.submit_callback()
        async def author_modal_callback(interaction: discord.Interaction):
            if (name := name_field.value):
                author_data['name'] = name
                author_data['icon_url'] = image_field.value
                author_data['url'] = link_field.value
                embed_data['author'] = author_data
            else:
                embed_data.pop('author', None)

            data['embed'] = embed_data

            await self.push_change(data)

            await interaction.response.defer()

        await press.response.send_modal(modal)

    async def author_button_refresh(self):
        t = self.bot.translator.t
        button = self.author_button
        button.label = t(_p(
            'ui:msg_editor|button:author|label',
            "Author"
        ))

    @button(label="FOOTER_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def footer_button(self, press: discord.Interaction, pressed: Button):
        """
        Open the Footer editor (edit footer icon, text, timestamp).
        """
        data = self.copy_data()
        embed_data = data.get('embed', {})
        footer_data = embed_data.get('footer', {})

        t = self.bot.translator.t

        text_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:footer|field:text|label',
                "Footer Text"
            )),
            style=TextStyle.long,
            required=False,
            default=footer_data.get('text', ''),
            max_length=2048
        )

        image_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:footer|field:image|label',
                "Footer Image URL"
            )),
            style=TextStyle.short,
            required=False,
            default=footer_data.get('icon_url', ''),
        )

        timestamp_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:footer|field:timestamp|label',
                "Embed Timestamp (in ISO format)"
            )),
            style=TextStyle.short,
            required=False,
            default=embed_data.get('timestamp', ''),
            placeholder=utc_now().replace(microsecond=0).isoformat(sep=' ')
        )

        modal = MsgEditorInput(
            text_field,
            image_field,
            timestamp_field,
            title=t(_p('ui:msg_editor|modal:footer|title', "Embed Footer Editor"))
        )

        @modal.submit_callback()
        async def footer_modal_callback(interaction: discord.Interaction):
            if (text := text_field.value):
                footer_data['text'] = text
                footer_data['icon_url'] = image_field.value
                embed_data['footer'] = footer_data
            else:
                embed_data.pop('footer', None)

            if (ts := timestamp_field.value):
                try:
                    dt.datetime.fromisoformat(ts)
                except ValueError:
                    raise UserInputError(
                        t(_p(
                            'ui:msg_editor|button:footer|error:invalid_timestamp',
                            "Invalid timestamp! Please enter the timestamp in ISO format."
                        ))
                    )
                embed_data['timestamp'] = ts
            else:
                embed_data.pop('timestamp', None)

            data['embed'] = embed_data

            await self.push_change(data)

            await interaction.response.defer()

        await press.response.send_modal(modal)

    async def footer_button_refresh(self):
        t = self.bot.translator.t
        button = self.footer_button
        button.label = t(_p(
            'ui:msg_editor|button:footer|label',
            "Footer"
        ))

    @button(label="IMAGES_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def images_button(self, press: discord.Interaction, pressed: Button):
        """
        Edit the embed images (thumbnail and main image).
        """
        data = self.copy_data()
        embed_data = data.get('embed', {})
        thumb_data = embed_data.get('thumbnail', {})
        image_data = embed_data.get('image', {})

        t = self.bot.translator.t

        thumb_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:images|field:thumb|label',
                "Thumbnail Image URL"
            )),
            style=TextStyle.short,
            required=False,
            default=thumb_data.get('url', ''),
        )

        image_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:images|field:image|label',
                "Embed Image URL"
            )),
            style=TextStyle.short,
            required=False,
            default=image_data.get('url', ''),
        )

        modal = MsgEditorInput(
            thumb_field,
            image_field,
            title=t(_p('ui:msg_editor|modal:images|title', "Embed images Editor"))
        )

        @modal.submit_callback()
        async def images_modal_callback(interaction: discord.Interaction):
            if (thumb_url := thumb_field.value):
                thumb_data['url'] = thumb_url
                embed_data['thumbnail'] = thumb_data
            else:
                embed_data.pop('thumbnail', None)

            if (image_url := image_field.value):
                image_data['url'] = image_url
                embed_data['image'] = image_data
            else:
                embed_data.pop('image', None)

            data['embed'] = embed_data

            await self.push_change(data)

            await interaction.response.defer()

        await press.response.send_modal(modal)

    async def images_button_refresh(self):
        t = self.bot.translator.t
        button = self.images_button
        button.label = t(_p(
            'ui:msg_editor|button:images|label',
            "Images"
        ))

    @button(label="ADD_FIELD_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def add_field_button(self, press: discord.Interaction, pressed: Button):
        """
        Add an embed field (position, name, value, inline)
        """
        data = self.copy_data()
        embed_data = data.get('embed', {})
        field_data = embed_data.get('fields', [])
        orig_fields = field_data.copy()

        t = self.bot.translator.t

        position_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:add_field|field:position|label',
                "Field number to insert at"
            )),
            style=TextStyle.short,
            required=True,
            default=str(len(field_data)),
        )

        name_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:add_field|field:name|label',
                "Field name"
            )),
            style=TextStyle.short,
            required=False,
            max_length=256,
        )

        value_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:add_field|field:value|label',
                "Field value"
            )),
            style=TextStyle.long,
            required=True,
            max_length=1024,
        )

        inline_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:add_field|field:inline|label',
                "Whether the field is inline"
            )),
            placeholder=t(_p(
                'ui:msg_editor|modal:add_field|field:inline|placeholder',
                "True/False"
            )),
            style=TextStyle.short,
            required=True,
            max_length=256,
            default='True',
        )

        modal = MsgEditorInput(
            name_field,
            value_field,
            position_field,
            inline_field,
            title=t(_p('ui:msg_editor|modal:add_field|title', "Add Embed Field"))
        )

        @modal.submit_callback()
        async def add_field_modal_callback(interaction: discord.Interaction):
            if inline_field.value.lower() == 'true':
                inline = True
            else:
                inline = False
            field = {
                'name': name_field.value,
                'value': value_field.value,
                'inline': inline
            }
            try:
                position = int(position_field.value)
            except ValueError:
                raise UserInputError(
                    t(_p(
                        'ui:msg_editor|modal:add_field|error:position_not_int',
                        "The field position must be an integer!"
                    ))
                )
            field_data = orig_fields.copy()
            field_data.insert(position, field)
            embed_data['fields'] = field_data
            data['embed'] = embed_data

            await self.push_change(data)

            await interaction.response.defer()

        await press.response.send_modal(modal)

    async def add_field_button_refresh(self):
        t = self.bot.translator.t
        button = self.add_field_button
        button.label = t(_p(
            'ui:msg_editor|button:add_field|label',
            "Add Field"
        ))
        data = self.history[-1]
        embed_data = data.get('embed', {})
        field_data = embed_data.get('fields', [])
        button.disabled = (len(field_data) >= 25)

    def _field_option(self, index, field_data):
        t = self.bot.translator.t

        name = field_data.get('name', "")
        value = field_data['value']

        if not name:
            name = t(_p(
                'ui:msg_editor|format_field|name_placeholder',
                "-"
            ))

        name = f"{index+1}. {name}"
        if len(name) > 100:
            name = name[:97] + '...'

        if len(value) > 100:
            value = value[:97] + '...'

        return SelectOption(label=name, description=value, value=str(index))

    @select(cls=Select, placeholder="EDIT_FIELD_MENU_PLACEHOLDER", max_values=1)
    async def edit_field_menu(self, selection: discord.Interaction, selected: Select):
        if not selected.values:
            await selection.response.defer()
            return

        index = int(selected.values[0])
        data = self.copy_data()
        embed_data = data.get('embed', {})
        field_data = embed_data.get('fields', [])
        field = field_data[index]

        t = self.bot.translator.t

        name_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:edit_field|field:name|label',
                "Field name"
            )),
            style=TextStyle.short,
            default=field.get('name', ''),
            required=False,
            max_length=256,
        )

        value_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:edit_field|field:value|label',
                "Field value"
            )),
            style=TextStyle.long,
            default=field.get('value', ''),
            required=True,
            max_length=1024,
        )

        inline_field = TextInput(
            label=t(_p(
                'ui:msg_editor|modal:edit_field|field:inline|label',
                "Whether the field is inline"
            )),
            placeholder=t(_p(
                'ui:msg_editor|modal:edit_field|field:inline|placeholder',
                "True/False"
            )),
            default='True' if field.get('inline', True) else 'False',
            style=TextStyle.short,
            required=True,
            max_length=256,
        )

        modal = MsgEditorInput(
            name_field,
            value_field,
            inline_field,
            title=t(_p('ui:msg_editor|modal:edit_field|title', "Edit Embed Field"))
        )

        @modal.submit_callback()
        async def edit_field_modal_callback(interaction: discord.Interaction):
            if inline_field.value.lower() == 'true':
                inline = True
            else:
                inline = False
            field = {
                'name': name_field.value,
                'value': value_field.value,
                'inline': inline
            }
            field_data[index] = field
            embed_data['fields'] = field_data
            data['embed'] = embed_data

            await self.push_change(data)

            await interaction.response.defer()

        await selection.response.send_modal(modal)

    async def edit_field_menu_refresh(self):
        t = self.bot.translator.t
        menu = self.edit_field_menu
        menu.placeholder = t(_p(
            'ui:msg_editor|menu:edit_field|placeholder',
            "Edit Embed Field"
        ))
        data = self.history[-1]
        embed_data = data.get('embed', {})
        field_data = embed_data.get('fields', [])

        if len(field_data) == 0:
            menu.disabled = True
            menu.options = [
                SelectOption(label='Dummy')
            ]
        else:
            menu.disabled = False
            menu.options = [
                self._field_option(i, field)
                for i, field in enumerate(field_data)
            ]

    @select(cls=Select, placeholder="DELETE_FIELD_MENU_PLACEHOLDER", max_values=1)
    async def delete_field_menu(self, selection: discord.Interaction, selected: Select):
        if not selected.values:
            await selection.response.defer()
            return

        index = int(selected.values[0])
        data = self.copy_data()
        embed_data = data.get('embed', {})
        field_data = embed_data.get('fields', [])
        field_data.pop(index)
        if not field_data:
            embed_data.pop('fields')
        await self.push_change(data)
        await selection.response.defer()

    async def delete_field_menu_refresh(self):
        t = self.bot.translator.t
        menu = self.delete_field_menu
        menu.placeholder = t(_p(
            'ui:msg_deleteor|menu:delete_field|placeholder',
            "Remove Embed Field"
        ))
        data = self.history[-1]
        embed_data = data.get('embed', {})
        field_data = embed_data.get('fields', [])

        if len(field_data) == 0:
            menu.disabled = True
            menu.options = [
                SelectOption(label='Dummy')
            ]
        else:
            menu.disabled = False
            menu.options = [
                self._field_option(i, field)
                for i, field in enumerate(field_data)
            ]

    # -- Shared --
    @button(label="SAVE_BUTTON_PLACEHOLDER", style=ButtonStyle.green)
    async def save_button(self, press: discord.Interaction, pressed: Button):
        """
        Saving simply resets the undo stack and calls the callback function.
        Presumably the callback is hooked up to data or similar.
        """
        await press.response.defer(thinking=True, ephemeral=True)
        if self._callback is not None:
            await self._callback(self.data)
        self.history = self.history[-1:]
        await self.refresh(thinking=press)

    async def save_button_refresh(self):
        t = self.bot.translator.t
        button = self.save_button
        button.label = t(_p(
            'ui:msg_editor|button:save|label',
            "Save"
        ))
        if len(self.history) > 1:
            original = json.dumps(self.history[0])
            current = json.dumps(self.history[-1])
            button.disabled = (original == current)
        else:
            button.disabled = True

    @button(label="DOWNLOAD_BUTTON_PLACEHOLDER", style=ButtonStyle.grey)
    async def download_button(self, press: discord.Interaction, pressed: Button):
        """
        Reply ephemerally with a formatted json version of the message content.
        """
        data = json.dumps(self.history[-1], indent=2)
        with StringIO(data) as fp:
            fp.seek(0)
            file = discord.File(fp, filename='message.json')
            await press.response.send_message(file=file, ephemeral=True)

    async def download_button_refresh(self):
        t = self.bot.translator.t
        button = self.download_button
        button.label = t(_p(
            'ui:msg_editor|button:download|label',
            "Download"
        ))

    @button(label="UNDO_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def undo_button(self, press: discord.Interaction, pressed: Button):
        """
        Pop the history stack.
        """
        if len(self.history) > 1:
            state = self.history.pop()
            self.future.append(state)
        await press.response.defer()
        await self.refresh()

    async def undo_button_refresh(self):
        t = self.bot.translator.t
        button = self.undo_button
        button.label = t(_p(
            'ui:msg_editor|button:undo|label',
            "Undo"
        ))
        button.disabled = (len(self.history) <= 1)

    @button(label="REDO_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def redo_button(self, press: discord.Interaction, pressed: Button):
        """
        Pop the future stack.
        """
        if len(self.future) > 0:
            state = self.future.pop()
            self.history.append(state)
        await press.response.defer()
        await self.refresh()

    async def redo_button_refresh(self):
        t = self.bot.translator.t
        button = self.redo_button
        button.label = t(_p(
            'ui:msg_editor|button:redo|label',
            "Redo"
        ))
        button.disabled = (len(self.future) == 0)

    @button(style=ButtonStyle.grey, emoji=conf.emojis.cancel)
    async def quit_button(self, press: discord.Interaction, pressed: Button):
        # Confirm quit if there are unsaved changes
        unsaved = False
        if len(self.history) > 1:
            original = json.dumps(self.history[0])
            current = json.dumps(self.history[-1])
            if original != current:
                unsaved = True

        # Confirmation prompt
        if unsaved:
            t = self.bot.translator.t
            confirm_msg = t(_p(
                'ui:msg_editor|button:quit|confirm',
                "You have unsaved changes! Are you sure you want to quit?"
            ))
            confirm = Confirm(confirm_msg, self._callerid)
            confirm.confirm_button.label = t(_p(
                'ui:msg_editor|button:quit|confirm|button:yes',
                "Yes, Quit Now"
            ))
            confirm.confirm_button.style = ButtonStyle.red
            confirm.cancel_button.style = ButtonStyle.green
            confirm.cancel_button.label = t(_p(
                'ui:msg_editor|button:quit|confirm|button:no',
                "No, Go Back"
            ))
            try:
                result = await confirm.ask(press, ephemeral=True)
            except ResponseTimedOut:
                result = False

            if result:
                await self.quit()
        else:
            await self.quit()

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        data = self.copy_data()
        await self.format_data(data)

        args = {}
        args['content'] = data.get('content', '')

        if 'embed' in data:
            args['embed'] = discord.Embed.from_dict(data['embed'])
        else:
            args['embed'] = None

        return MessageArgs(**args)

    async def refresh_layout(self):
        to_refresh = (
            self.edit_button_refresh(),
            self.add_embed_button_refresh(),
            self.body_button_refresh(),
            self.author_button_refresh(),
            self.footer_button_refresh(),
            self.images_button_refresh(),
            self.add_field_button_refresh(),
            self.edit_field_menu_refresh(),
            self.delete_field_menu_refresh(),
            self.save_button_refresh(),
            self.download_button_refresh(),
            self.undo_button_refresh(),
            self.redo_button_refresh(),
            self.rm_embed_button_refresh(),
        )
        await asyncio.gather(*to_refresh)

        if self.history[-1].get('embed', None):
            self.set_layout(
                (self.body_button, self.author_button, self.footer_button, self.images_button, self.add_field_button),
                (self.edit_field_menu,),
                (self.delete_field_menu,),
                (self.rm_embed_button,),
                (self.save_button, self.download_button, self.undo_button, self.redo_button, self.quit_button),
            )
        else:
            self.set_layout(
                (self.edit_button, self.add_embed_button),
                (self.save_button, self.download_button, self.undo_button, self.redo_button, self.quit_button),
            )

    async def reload(self):
        # All data is handled by components, so nothing to do here
        pass

    async def redraw(self, thinking: Optional[discord.Interaction] = None):
        """
        Overriding MessageUI.redraw to propagate exception.
        """
        await self.refresh_layout()
        args = await self.make_message()

        if thinking is not None and not thinking.is_expired() and thinking.response.is_done():
            asyncio.create_task(thinking.delete_original_response())

        if self._original and not self._original.is_expired():
            await self._original.edit_original_response(**args.edit_args, view=self)
        elif self._message:
            await self._message.edit(**args.edit_args, view=self)
        else:
            # Interaction expired or already closed. Quietly cleanup.
            await self.close()

    async def pre_timeout(self):
        unsaved = False
        if len(self.history) > 1:
            original = json.dumps(self.history[0])
            current = json.dumps(self.history[-1])
            if original != current:
                unsaved = True

        # Timeout confirmation
        if unsaved:
            t = self.bot.translator.t
            grace_period = 60
            grace_time = utc_now() + dt.timedelta(seconds=grace_period)
            embed = discord.Embed(
                title=t(_p(
                    'ui:msg_editor|timeout_warning|title',
                    "Warning!"
                )),
                description=t(_p(
                    'ui:msg_editor|timeout_warning|desc',
                    "This interface will time out {timestamp}. Press 'Continue' below to keep editing."
                )).format(
                    timestamp=discord.utils.format_dt(grace_time, style='R')
                ),
            )

            components = None
            stopped = False

            @AButton(label=t(_p('ui:msg_editor|timeout_warning|continue', "Continue")), style=ButtonStyle.green)
            async def cont_button(interaction: discord.Interaction, pressed):
                await interaction.response.defer()
                await interaction.message.delete()
                nonlocal stopped
                stopped = True
                # TODO: Clean up this mess. It works, but needs to be refactored to a timeout confirmation mixin.
                # TODO: Consider moving the message to the interaction response
                self._refresh_timeout()
                components.stop()

            components = AsComponents(cont_button, timeout=grace_period)
            message = await self._original.channel.send(content=f"<@{self._callerid}>", embed=embed, view=components)
            await components.wait()

            if not stopped:
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass
