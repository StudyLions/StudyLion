from .connection import _replace_char

from meta import sharding


class Condition:
    """
    ABC representing a selection condition.
    """
    __slots__ = ()

    def apply(self, key, values, conditions):
        raise NotImplementedError


class NOT(Condition):
    __slots__ = ('value',)

    def __init__(self, value):
        self.value = value

    def apply(self, key, values, conditions):
        item = self.value
        if isinstance(item, (list, tuple)):
            if item:
                conditions.append("{} NOT IN ({})".format(key, ", ".join([_replace_char] * len(item))))
                values.extend(item)
            else:
                raise ValueError("Cannot check an empty iterable!")
        else:
            conditions.append("{}!={}".format(key, _replace_char))
            values.append(item)


class GEQ(Condition):
    __slots__ = ('value',)

    def __init__(self, value):
        self.value = value

    def apply(self, key, values, conditions):
        item = self.value
        if isinstance(item, (list, tuple)):
            raise ValueError("Cannot apply GEQ condition to a list!")
        else:
            conditions.append("{} >= {}".format(key, _replace_char))
            values.append(item)


class LEQ(Condition):
    __slots__ = ('value',)

    def __init__(self, value):
        self.value = value

    def apply(self, key, values, conditions):
        item = self.value
        if isinstance(item, (list, tuple)):
            raise ValueError("Cannot apply LEQ condition to a list!")
        else:
            conditions.append("{} <= {}".format(key, _replace_char))
            values.append(item)


class Constant(Condition):
    __slots__ = ('value',)

    def __init__(self, value):
        self.value = value

    def apply(self, key, values, conditions):
        conditions.append("{} {}".format(key, self.value))


class SHARDID(Condition):
    __slots__ = ('shardid', 'shard_count')

    def __init__(self, shardid, shard_count):
        self.shardid = shardid
        self.shard_count = shard_count

    def apply(self, key, values, conditions):
        conditions.append("({} >> 22) %% {} = {}".format(key, self.shard_count, _replace_char))
        values.append(self.shardid)


THIS_SHARD = SHARDID(sharding.shard_number, sharding.shard_count)


NULL = Constant('IS NULL')
NOTNULL = Constant('IS NOT NULL')
