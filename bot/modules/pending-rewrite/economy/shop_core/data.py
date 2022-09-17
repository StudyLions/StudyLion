from cachetools import LRUCache

from data import Table, RowTable


shop_items = Table('shop_items')

colour_roles = Table('shop_items_colour_roles', attach_as='colour_roles')


shop_item_info = RowTable(
    'shop_item_info',
    ('itemid',
     'guildid', 'item_type', 'price', 'purchasable', 'deleted', 'created_at',
     'roleid',  # Colour roles
     ),
    'itemid',
    cache=LRUCache(1000)
)
