from itertools import chain
from psycopg2.extras import execute_values

from .connection import conn
from .formatters import (_format_updatestr, _format_conditions, _format_insertkeys,
                         _format_selectkeys, _format_insertvalues)


def select_where(table, select_columns=None, cursor=None, _extra='', **conditions):
    """
    Select rows from the given table matching the conditions
    """
    criteria, criteria_values = _format_conditions(conditions)
    col_str = _format_selectkeys(select_columns)

    if criteria:
        where_str = "WHERE {}".format(criteria)
    else:
        where_str = ""

    cursor = cursor or conn.cursor()
    cursor.execute(
        'SELECT {} FROM {} {} {}'.format(col_str, table, where_str, _extra),
        criteria_values
    )
    return cursor.fetchall()


def update_where(table, valuedict, cursor=None, **conditions):
    """
    Update rows in the given table matching the conditions
    """
    key_str, key_values = _format_updatestr(valuedict)
    criteria, criteria_values = _format_conditions(conditions)

    if criteria:
        where_str = "WHERE {}".format(criteria)
    else:
        where_str = ""

    cursor = cursor or conn.cursor()
    cursor.execute(
        'UPDATE {} SET {} {} RETURNING *'.format(table, key_str, where_str),
        tuple((*key_values, *criteria_values))
    )
    return cursor.fetchall()


def delete_where(table, cursor=None, **conditions):
    """
    Delete rows in the given table matching the conditions
    """
    criteria, criteria_values = _format_conditions(conditions)

    if criteria:
        where_str = "WHERE {}".format(criteria)
    else:
        where_str = ""

    cursor = cursor or conn.cursor()
    cursor.execute(
        'DELETE FROM {} {} RETURNING *'.format(table, where_str),
        criteria_values
    )
    return cursor.fetchall()


def insert(table, cursor=None, allow_replace=False, **values):
    """
    Insert the given values into the table
    """
    keys, values = zip(*values.items())

    key_str = _format_insertkeys(keys)
    value_str, values = _format_insertvalues(values)

    action = 'REPLACE' if allow_replace else 'INSERT'

    cursor = cursor or conn.cursor()
    cursor.execute(
        '{} INTO {} {} VALUES {} RETURNING *'.format(action, table, key_str, value_str),
        values
    )
    return cursor.fetchone()


def insert_many(table, *value_tuples, insert_keys=None, cursor=None):
    """
    Insert all the given values into the table
    """
    key_str = _format_insertkeys(insert_keys)
    value_strs, value_tuples = zip(*(_format_insertvalues(value_tuple) for value_tuple in value_tuples))

    value_str = ", ".join(value_strs)
    values = tuple(chain(*value_tuples))

    cursor = cursor or conn.cursor()
    cursor.execute(
        'INSERT INTO {} {} VALUES {} RETURNING *'.format(table, key_str, value_str),
        values
    )
    return cursor.fetchall()


def upsert(table, constraint, cursor=None, **values):
    """
    Insert or on conflict update.
    """
    valuedict = values
    keys, values = zip(*values.items())

    key_str = _format_insertkeys(keys)
    value_str, values = _format_insertvalues(values)
    update_key_str, update_key_values = _format_updatestr(valuedict)

    if not isinstance(constraint, str):
        constraint = ", ".join(constraint)

    cursor = cursor or conn.cursor()
    cursor.execute(
        'INSERT INTO {} {} VALUES {} ON CONFLICT({}) DO UPDATE SET {} RETURNING *'.format(
            table, key_str, value_str, constraint, update_key_str
        ),
        tuple((*values, *update_key_values))
    )
    return cursor.fetchone()


def update_many(table, *values, set_keys=None, where_keys=None, cursor=None):
    cursor = cursor or conn.cursor()

    return execute_values(
        cursor,
        """
        UPDATE {table}
        SET {set_clause}
        FROM (VALUES %s)
        AS {temp_table}
        WHERE {where_clause}
        RETURNING *
        """.format(
            table=table,
            set_clause=', '.join("{0} = _t.{0}".format(key) for key in set_keys),
            where_clause=' AND '.join("{1}.{0} = _t.{0}".format(key, table) for key in where_keys),
            temp_table="_t ({})".format(', '.join(set_keys + where_keys))
        ),
        values,
        fetch=True
    )
