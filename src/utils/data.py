"""
Some useful pre-built Conditions for data queries.
"""
from typing import Optional, Any
from itertools import chain

from psycopg import sql
from data.conditions import Condition, Joiner
from data.columns import ColumnExpr
from data.base import Expression
from constants import MAX_COINS


def MULTIVALUE_IN(columns: tuple[str, ...], *data: tuple[Any, ...]) -> Condition:
    """
    Condition constructor for filtering by multiple column equalities.

    Example Usage
    -------------
    Query.where(MULTIVALUE_IN(('guildid', 'userid'), (1, 2), (3, 4)))
    """
    if not data:
        raise ValueError("Cannot create empty multivalue condition.")
    left = sql.SQL("({})").format(
        sql.SQL(', ').join(
            sql.Identifier(key)
            for key in columns
        )
    )
    right_item = sql.SQL('({})').format(
        sql.SQL(', ').join(
            sql.Placeholder()
            for _ in columns
        )
    )
    right = sql.SQL("({})").format(
        sql.SQL(', ').join(
            right_item
            for _ in data
        )
    )
    return Condition(
        left,
        Joiner.IN,
        right,
        chain(*data)
    )


def MEMBERS(*memberids: tuple[int, int], guild_column='guildid', user_column='userid') -> Condition:
    """
    Condition constructor for filtering member tables by guild and user id simultaneously.

    Example Usage
    -------------
    Query.where(MEMBERS((1234,12), (5678,34)))
    """
    if not memberids:
        raise ValueError("Cannot create a condition with no members")
    return Condition(
        sql.SQL("({guildid}, {userid})").format(
            guildid=sql.Identifier(guild_column),
            userid=sql.Identifier(user_column)
        ),
        Joiner.IN,
        sql.SQL("({})").format(
            sql.SQL(', ').join(
                sql.SQL("({}, {})").format(
                    sql.Placeholder(),
                    sql.Placeholder()
                ) for _ in memberids
            )
        ),
        chain(*memberids)
    )


def as_duration(expr: Expression) -> ColumnExpr:
    """
    Convert an integer expression into a duration expression.
    """
    expr_expr, expr_values = expr.as_tuple()
    return ColumnExpr(
        sql.SQL("({} * interval '1 second')").format(expr_expr),
        expr_values
    )


class TemporaryTable(Expression):
    """
    Create a temporary table expression to be used in From or With clauses.

    Example
    -------
    ```
    tmp_table = TemporaryTable('_col1', '_col2', name='data')
    tmp_table.values((1, 2), (3, 4))

    real_table.update_where(col1=tmp_table['_col1']).set(col2=tmp_table['_col2']).from_(tmp_table)
    ```
    """

    def __init__(self, *columns: str, name: str = '_t', types: Optional[tuple[str, ...]] = None):
        self.name = name
        self.columns = columns
        self.types = types
        if types and len(types) != len(columns):
            raise ValueError("Number of types does not much number of columns!")

        self._table_columns = {
            col: ColumnExpr(sql.Identifier(name, col))
            for col in columns
        }

        self.values = []

    def __getitem__(self, key) -> sql.Identifier:
        return self._table_columns[key]

    def as_tuple(self):
        """
        (VALUES {})
        AS
        name (col1, col2)
        """
        if not self.values:
            raise ValueError("Cannot flatten CTE with no values.")

        single_value = sql.SQL("({})").format(sql.SQL(", ").join(sql.Placeholder() for _ in self.columns))
        if self.types:
            first_value = sql.SQL("({})").format(
                sql.SQL(", ").join(
                    sql.SQL("{}::{}").format(sql.Placeholder(), sql.SQL(cast))
                    for cast in self.types
                )
            )
        else:
            first_value = single_value

        value_placeholder = sql.SQL("(VALUES {})").format(
            sql.SQL(", ").join(
                (first_value, *(single_value for _ in self.values[1:]))
            )
        )
        expr = sql.SQL("{values} AS {name} ({columns})").format(
            values=value_placeholder,
            name=sql.Identifier(self.name),
            columns=sql.SQL(", ").join(sql.Identifier(col) for col in self.columns)
        )
        values = chain(*self.values)
        return (expr, values)

    def set_values(self, *data):
        self.values = data


def SAFECOINS(expr: Expression) -> Expression:
    expr_expr, expr_values = expr.as_tuple()
    return ColumnExpr(
        sql.SQL("LEAST({}, {})").format(
            expr_expr,
            sql.Literal(MAX_COINS)
        ),
        expr_values
    )
