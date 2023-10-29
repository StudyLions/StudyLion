from abc import abstractmethod
from typing import Any, Protocol, runtime_checkable
from itertools import chain
from psycopg import sql


@runtime_checkable
class Expression(Protocol):
    __slots__ = ()

    @abstractmethod
    def as_tuple(self) -> tuple[sql.Composable, tuple[Any, ...]]:
        raise NotImplementedError


class RawExpr(Expression):
    __slots__ = ('expr', 'values')

    expr: sql.Composable
    values: tuple[Any, ...]

    def __init__(self, expr: sql.Composable, values: tuple[Any, ...] = ()):
        self.expr = expr
        self.values = values

    def as_tuple(self):
        return (self.expr, self.values)

    @classmethod
    def join(cls, *expressions: Expression, joiner: sql.SQL = sql.SQL(' ')):
        """
        Join a sequence of Expressions into a single RawExpr.
        """
        tups = (
            expression.as_tuple()
            for expression in expressions
        )
        return cls.join_tuples(*tups, joiner=joiner)

    @classmethod
    def join_tuples(cls, *tuples: tuple[sql.Composable, tuple[Any, ...]], joiner: sql.SQL = sql.SQL(' ')):
        exprs, values = zip(*tuples)
        expr = joiner.join(exprs)
        value = tuple(chain(*values))
        return cls(expr, value)
