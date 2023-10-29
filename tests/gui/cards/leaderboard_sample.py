import asyncio
import datetime as dt
from src.cards import LeaderboardCard


async def get_card():
    card = await LeaderboardCard.generate_sample()
    with open('samples/leaderboard-sample.png', 'wb') as image_file:
        image_file.write(card.fp.read())

if __name__ == '__main__':
    asyncio.run(get_card())
