from .connection import _replace_char


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


class Constant(Condition):
    __slots__ = ('value',)

    def __init__(self, value):
        self.value = value

    def apply(self, key, values, conditions):
        conditions.append("{} {}".format(key, self.value))


NULL = Constant('IS NULL')
NOTNULL = Constant('IS NOT NULL')
