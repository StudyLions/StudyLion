from typing import Optional
import asyncio
from io import BytesIO

from PIL import Image

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds

from discord.ui.button import button

from utils.lib import error_embed
from utils.ui import LeoUI

from meta import LionCog, LionBot, LionContext


emoji_rotate_cw = "↩️"
emoji_rotate_ccw = "↪️"
emoji_close = "❌"


class ParaCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot

    @cmds.hybrid_command(
        name="quote",
        description="Quote a previous message by id from this or another channel."
    )
    @appcmds.describe(
        message_id="Message id of the message you want to quote."
    )
    async def quote_cmd(self, ctx: LionContext, message_id: str):
        message_id = message_id.strip()

        if not message_id or not message_id.isdigit():
            await ctx.error_reply("Please provide a valid message id.")

        msgid = int(message_id)

        if ctx.interaction:
            await ctx.interaction.response.defer(thinking=True)

            # Look in the current channel
            message = None
            try:
                message = await ctx.channel.fetch_message(msgid)
            except discord.HTTPException:
                pass

            if message is None:
                # Search for the message in other channels
                channels = [channel for channel in ctx.guild.text_channels if channel.id != ctx.channel.id]
                message = await self.message_seeker(msgid, channels)

            if message is None:
                # We couldn't find the message in any of the channels the user could see.
                embed = discord.Embed(
                    title="Message not found!",
                    colour=discord.Colour.red(),
                    description=f"Could not find a message in this server with the id `{msgid}`"
                )
            else:
                content = message.content
                header = f"[Click to jump to message]({message.jump_url})"
                content = (
                    '\n'.join(f"> {line}" for line in message.content.splitlines()) + '\n' + header
                )
                embed = discord.Embed(
                    description=content,
                    colour=discord.Colour.light_grey(),
                    timestamp=message.created_at
                )
                embed.set_author(name=message.author.name, icon_url=message.author.avatar.url)
                embed.set_footer(text=f"Sent in #{message.channel.name}")

            await ctx.interaction.edit_original_response(embed=embed)

    async def message_seeker(self, msgid: int, channels: list[discord.TextChannel]):
        tasks = []
        for channel in channels:
            task = asyncio.create_task(self.channel_message_seeker(channel, msgid))
            tasks.append(task)

        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result is None:
                continue
            else:
                for task in tasks:
                    task.cancel()
                return result

        return None

    async def channel_message_seeker(self, channel, msgid):
        try:
            message = await channel.fetch_message(msgid)
        except discord.HTTPException:
            return None
        else:
            return message

    @cmds.hybrid_command(
        name='rotate',
        description="Rotate an image sent in the last 10 messages."
    )
    @appcmds.describe(
        angle="Angle to rotate in degrees anticlockwise."
    )
    async def rotate_cmd(self, ctx: LionContext, angle: Optional[int] = 90):
        await ctx.interaction.response.defer(thinking=True)

        image_url = None
        async for message in ctx.channel.history(limit=10):
            if (
                message.attachments and
                message.attachments[-1].content_type.startswith('image')
            ):
                image_url = message.attachments[-1].proxy_url
                break

            for embed in reversed(message.embeds):
                if embed.type == 'image':
                    image_url = embed.url
                    break
                elif embed.type == 'rich':
                    if embed.image:
                        image_url = embed.image.proxy_url
                        break

        if image_url is None:
            await ctx.interaction.edit_original_response(
                embed=error_embed("Could not find an image in the last 10 images.")
            )
        else:
            # We have an image, now rotate it.
            async with ctx.bot.web_client.get(image_url) as r:
                if r.status == 200:
                    response = await r.read()
                else:
                    return await ctx.interaction.edit_original_response(
                        embed=error_embed("Retrieving the previous image failed.")
                    )
            with Image.open(BytesIO(response)) as im:
                ui = RotateUI(im, str(ctx.author.id))
                await ui.run(ctx.interaction, angle)


class RotateUI(LeoUI):
    def __init__(self, image, name):
        super().__init__()
        self.original = image
        self.filename = name

        self._out_message: Optional[discord.Message] = None
        self._rotated: Optional[Image] = None
        self._interaction: Optional[discord.Interaction] = None
        self._angle = 0

    @button(emoji=emoji_rotate_ccw)
    async def press_ccw(self, interaction, press):
        await interaction.response.defer()
        self._angle += 90
        await self.update()

    @button(emoji=emoji_close)
    async def press_close(self, interaction, press):
        await interaction.response.defer()
        await self._interaction.delete_original_response()
        await self.close()

    @button(emoji=emoji_rotate_cw)
    async def press_cw(self, interaction, press):
        await interaction.response.defer()
        self._angle -= 90
        await self.update()

    async def cleanup(self):
        if self.original:
            self.original.close()

    async def run(self, interaction, angle: int):
        self._angle = angle
        self._interaction = interaction
        await self.update()
        await self.wait()

    async def update(self):
        with self._rotate() as rotated:
            with BytesIO() as output:
                self.save_into(rotated, output)
                await self._interaction.edit_original_response(
                    attachments=[discord.File(output, filename=f"{self.filename}.jpg")],
                    view=self
                )

    def save_into(self, rotated, output):
        exif = self.original.info.get('exif', None)
        if exif:
            rotated.convert('RGB').save(output, exif=exif, format="JPEG", quality=85, optimize=True)
        else:
            rotated.convert("RGB").save(output, format="JPEG", quality=85, optimize=True)
        output.seek(0)

    def _rotate(self):
        """
        Rotate original image by the provided amount.
        """
        im = self.original
        with im.rotate(self._angle, expand=1) as rotated:
            bbox = rotated.getbbox()
            return rotated.crop(bbox)
