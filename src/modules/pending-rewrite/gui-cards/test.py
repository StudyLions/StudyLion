from io import BytesIO
from PIL import Image, ImageDraw
from .Card import Card
from .Avatars import avatar_manager


class TestCard(Card):
    server_route = "testing"

    def __init__(self, text, avatar):
        self.text = text
        self.avatar = avatar

        self.image = None

    def draw(self):
        bg = Image.new('RGBA', (100, 100))
        draw = ImageDraw.Draw(bg)
        draw.text(
            (0, 0),
            self.text,
            fill='#FF0000'
        )
        bg.alpha_composite(self.avatar, (0, 30))

        return bg

    @classmethod
    async def card_route(cls, executor, args, kwargs):
        kwargs['avatar'] = (await avatar_manager().get_avatars(kwargs['avatar']))[0]
        return await super().card_route(executor, args, kwargs)

    @classmethod
    def _execute(cls, *args, **kwargs):
        with BytesIO(kwargs['avatar']) as image_data:
            with Image.open(image_data).convert('RGBA') as avatar_image:
                kwargs['avatar'] = avatar_image
                return super()._execute(*args, **kwargs)
