# from meta import sharding
from typing import Any, Union
from enum import Enum
from itertools import chain
from psycopg import sql

from .base import Expression, RawExpr


"""
A Condition is a "logical" database expression, intended for use in Where statements.
Conditions support bitwise logical operators ~, &, |, each producing another Condition.
"""

NULL = None


class Joiner(Enum):
    EQUALS = ('=', '!=')
    IS = ('IS', 'IS NOT')
    LIKE = ('LIKE', 'NOT LIKE')
    BETWEEN = ('BETWEEN', 'NOT BETWEEN')
    IN = ('IN', 'NOT IN')
    LT = ('<', '>=')
    LE = ('<=', '>')
    NONE = ('', '')


class Condition(Expression):
    __slots__ = ('expr1', 'joiner', 'negated', 'expr2', 'values')

    def __init__(self,
                 expr1: sql.Composable, joiner: Joiner = Joiner.NONE, expr2: sql.Composable = sql.SQL(''),
                 values: tuple[Any, ...] = (), negated=False
                 ):
        self.expr1 = expr1
        self.joiner = joiner
        self.negated = negated
        self.expr2 = expr2
        self.values = values

    def as_tuple(self):
        expr = sql.SQL(' ').join((self.expr1, sql.SQL(self.joiner.value[self.negated]), self.expr2))
        if self.negated and self.joiner is Joiner.NONE:
            expr = sql.SQL("NOT ({})").format(expr)
        return (expr, self.values)

    @classmethod
    def construct(cls, *conditions: 'Condition', **kwargs: Union[Any, Expression]):
        """
        Construct a Condition from a sequence of Conditions,
        together with some explicit column conditions.
        """
        # TODO: Consider adding a _table identifier here so we can identify implicit columns
        # Or just require subquery type conditions to always come from modelled tables.
        implicit_conditions = (
            cls._expression_equality(RawExpr(sql.Identifier(column)), value) for column, value in kwargs.items()
        )
        return cls._and(*conditions, *implicit_conditions)

    @classmethod
    def _and(cls, *conditions: 'Condition'):
        if not len(conditions):
            raise ValueError("Cannot combine 0 Conditions")
        if len(conditions) == 1:
            return conditions[0]

        exprs, values = zip(*(condition.as_tuple() for condition in conditions))
        cond_expr = sql.SQL(' AND ').join((sql.SQL('({})').format(expr) for expr in exprs))
        cond_values = tuple(chain(*values))

        return Condition(cond_expr, values=cond_values)

    @classmethod
    def _or(cls, *conditions: 'Condition'):
        if not len(conditions):
            raise ValueError("Cannot combine 0 Conditions")
        if len(conditions) == 1:
            return conditions[0]

        exprs, values = zip(*(condition.as_tuple() for condition in conditions))
        cond_expr = sql.SQL(' OR ').join((sql.SQL('({})').format(expr) for expr in exprs))
        cond_values = tuple(chain(*values))

        return Condition(cond_expr, values=cond_values)

    @classmethod
    def _not(cls, condition: 'Condition'):
        condition.negated = not condition.negated
        return condition

    @classmethod
    def _expression_equality(cls, column: Expression, value: Union[Any, Expression]) -> 'Condition':
        # TODO: Check if this supports sbqueries
        col_expr, col_values = column.as_tuple()

        # TODO: Also support sql.SQL? For joins?
        if isinstance(value, Expression):
            # column = Expression
            value_expr, value_values = value.as_tuple()
            cond_exprs = (col_expr, Joiner.EQUALS, value_expr)
            cond_values = (*col_values, *value_values)
        elif isinstance(value, (tuple, list)):
            # column in (...)
            # TODO: Support expressions in value tuple?
            if not value:
                raise ValueError("Cannot create Condition from empty iterable!")
            value_expr = sql.SQL('({})').format(sql.SQL(',').join(sql.Placeholder() * len(value)))
            cond_exprs = (col_expr, Joiner.IN, value_expr)
            cond_values = (*col_values, *value)
        elif value is None:
            # column IS NULL
            cond_exprs = (col_expr, Joiner.IS, sql.NULL)
            cond_values = col_values
        else:
            # column = Literal
            cond_exprs = (col_expr, Joiner.EQUALS, sql.Placeholder())
            cond_values = (*col_values, value)

        return cls(cond_exprs[0], cond_exprs[1], cond_exprs[2], cond_values)

    def __invert__(self) -> 'Condition':
        self.negated = not self.negated
        return self

    def __and__(self, condition: 'Condition') -> 'Condition':
        return self._and(self, condition)

    def __or__(self, condition: 'Condition') -> 'Condition':
        return self._or(self, condition)


# Helper method to simply condition construction
def condition(*args, **kwargs) -> Condition:
    return Condition.construct(*args, **kwargs)


# class NOT(Condition):
#     __slots__ = ('value',)
#
#     def __init__(self, value):
#         self.value = value
#
#     def apply(self, key, values, conditions):
#         item = self.value
#         if isinstance(item, (list, tuple)):
#             if item:
#                 conditions.append("{} NOT IN ({})".format(key, ", ".join([_replace_char] * len(item))))
#                 values.extend(item)
#             else:
#                 raise ValueError("Cannot check an empty iterable!")
#         else:
#             conditions.append("{}!={}".format(key, _replace_char))
#             values.append(item)
#
#
# class GEQ(Condition):
#     __slots__ = ('value',)
#
#     def __init__(self, value):
#         self.value = value
#
#     def apply(self, key, values, conditions):
#         item = self.value
#         if isinstance(item, (list, tuple)):
#             raise ValueError("Cannot apply GEQ condition to a list!")
#         else:
#             conditions.append("{} >= {}".format(key, _replace_char))
#             values.append(item)
#
#
# class LEQ(Condition):
#     __slots__ = ('value',)
#
#     def __init__(self, value):
#         self.value = value
#
#     def apply(self, key, values, conditions):
#         item = self.value
#         if isinstance(item, (list, tuple)):
#             raise ValueError("Cannot apply LEQ condition to a list!")
#         else:
#             conditions.append("{} <= {}".format(key, _replace_char))
#             values.append(item)
#
#
# class Constant(Condition):
#     __slots__ = ('value',)
#
#     def __init__(self, value):
#         self.value = value
#
#     def apply(self, key, values, conditions):
#         conditions.append("{} {}".format(key, self.value))
#
#
# class SHARDID(Condition):
#     __slots__ = ('shardid', 'shard_count')
#
#     def __init__(self, shardid, shard_count):
#         self.shardid = shardid
#         self.shard_count = shard_count
#
#     def apply(self, key, values, conditions):
#         if self.shard_count > 1:
#             conditions.append("({} >> 22) %% {} = {}".format(key, self.shard_count, _replace_char))
#             values.append(self.shardid)
#
#
# # THIS_SHARD = SHARDID(sharding.shard_number, sharding.shard_count)
#
#
# NULL = Constant('IS NULL')
# NOTNULL = Constant('IS NOT NULL')
