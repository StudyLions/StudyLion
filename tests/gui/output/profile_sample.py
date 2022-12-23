from profile import ProfileCard


card = ProfileCard(
    name='ARI HORESH',
    discrim='#0001',
    avatar=open('samples/example_avatar.png', 'rb'),
    coins=58596,
    time=3750 * 3600,
    answers=10,
    attendance=0.9,
    badges=('MEDICINE', 'NEUROSCIENCE', 'BIO', 'MATHS', 'BACHELOR\'S DEGREE', 'VEGAN SOMETIMES', 'EUROPE'),
    achievements=(0, 2, 5, 7),
    current_rank=('VAMPIRE', 3000, 4000),
    next_rank=('WIZARD', 4000, 8000),
    draft=False
)
image = card.draw()
image.save('profilecard.png', dpi=(150, 150))
