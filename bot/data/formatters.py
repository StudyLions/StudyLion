from .connection import _replace_char
from .conditions import Condition


class _updateField:
    __slots__ = ()
    _EMPTY = object()  # Return value for `value` indicating no value should be added

    def key_field(self, key):
        raise NotImplementedError

    def value_field(self, key):
        raise NotImplementedError


class UpdateValue(_updateField):
    __slots__ = ('key_str', 'value')

    def __init__(self, key_str, value=_updateField._EMPTY):
        self.key_str = key_str
        self.value = value

    def key_field(self, key):
        return self.key_str.format(key=key, value=_replace_char, replace=_replace_char)

    def value_field(self, key):
        return self.value


class UpdateValueAdd(_updateField):
    __slots__ = ('value',)

    def __init__(self, value):
        self.value = value

    def key_field(self, key):
        return "{key} = {key} + {replace}".format(key=key, replace=_replace_char)

    def value_field(self, key):
        return self.value


def _format_conditions(conditions):
    """
    Formats a dictionary of conditions into a string suitable for 'WHERE' clauses.
    Supports `IN` type conditionals.
    """
    if not conditions:
        return ("", tuple())

    values = []
    conditional_strings = []
    for key, item in conditions.items():
        if isinstance(item, (list, tuple)):
            conditional_strings.append("{} IN ({})".format(key, ", ".join([_replace_char] * len(item))))
            values.extend(item)
        elif isinstance(item, Condition):
            item.apply(key, values, conditional_strings)
        else:
            conditional_strings.append("{}={}".format(key, _replace_char))
            values.append(item)

    return (' AND '.join(conditional_strings), values)


def _format_selectkeys(keys):
    """
    Formats a list of keys into a string suitable for `SELECT`.
    """
    if not keys:
        return "*"
    elif type(keys) is str:
        return keys
    else:
        return ", ".join(keys)


def _format_insertkeys(keys):
    """
    Formats a list of keys into a string suitable for `INSERT`
    """
    if not keys:
        return ""
    else:
        return "({})".format(", ".join(keys))


def _format_insertvalues(values):
    """
    Formats a list of values into a string suitable for `INSERT`
    """
    value_str = "({})".format(", ".join(_replace_char for value in values))
    return (value_str, values)


def _format_updatestr(valuedict):
    """
    Formats a dictionary of keys and values into a string suitable for 'SET' clauses.
    """
    if not valuedict:
        return ("", tuple())

    key_fields = []
    values = []
    for key, value in valuedict.items():
        if isinstance(value, _updateField):
            key_fields.append(value.key_field(key))
            v = value.value_field(key)
            if v is not _updateField._EMPTY:
                values.append(value.value_field(key))
        else:
            key_fields.append("{} = {}".format(key, _replace_char))
            values.append(value)

    return (', '.join(key_fields), values)
