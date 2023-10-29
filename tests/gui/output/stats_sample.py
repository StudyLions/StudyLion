import datetime as dt
from stats import StatsCard


card = StatsCard(
    (21, 123),
    (3600, 5 * 24 * 3600, 1.5 * 24 * 3600, 100 * 24 * 3600),
    50,
    [(1, 3), (7, 8), (10, 10), (12, 16), (18, 25), (27, 31)],
    date=dt.datetime(2022, 1, 1),
    # draft=True
)

image = card.draw()
image.save('statscard_alt.png', dpi=(150, 150))

card = StatsCard(
    (21, 123),
    (3600, 5 * 24 * 3600, 1.5 * 24 * 3600, 100 * 24 * 3600),
    50,
    [(1, 3), (7, 8), (10, 10), (12, 16), (18, 25), (27, 31)],
    date=dt.datetime(2022, 2, 1),
    # draft=True
)

image = card.draw()
image.save('statscard.png', dpi=(150, 150))
