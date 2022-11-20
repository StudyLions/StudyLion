from typing import Any, Union, TypeVar, Generic, Type, overload, Optional, TYPE_CHECKING
from psycopg import sql
from datetime import datetime

from .base import RawExpr, Expression
from .conditions import Condition, Joiner
from .table import Table


class ColumnExpr(RawExpr):
    __slots__ = ()

    def __lt__(self, obj) -> Condition:
        expr, values = self.as_tuple()

        if isinstance(obj, Expression):
            # column < Expression
            obj_expr, obj_values = obj.as_tuple()
            cond_exprs = (expr, Joiner.LT, obj_expr)
            cond_values = (*values, *obj_values)
        else:
            # column < Literal
            cond_exprs = (expr, Joiner.LT, sql.Placeholder())
            cond_values = (*values, obj)

        return Condition(cond_exprs[0], cond_exprs[1], cond_exprs[2], cond_values)

    def __le__(self, obj) -> Condition:
        expr, values = self.as_tuple()

        if isinstance(obj, Expression):
            # column <= Expression
            obj_expr, obj_values = obj.as_tuple()
            cond_exprs = (expr, Joiner.LE, obj_expr)
            cond_values = (*values, *obj_values)
        else:
            # column <= Literal
            cond_exprs = (expr, Joiner.LE, sql.Placeholder())
            cond_values = (*values, obj)

        return Condition(cond_exprs[0], cond_exprs[1], cond_exprs[2], cond_values)

    def __eq__(self, obj) -> Condition:  # type: ignore[override]
        return Condition._expression_equality(self, obj)

    def __ne__(self, obj) -> Condition:  # type: ignore[override]
        return ~(self.__eq__(obj))

    def __gt__(self, obj) -> Condition:
        return ~(self.__le__(obj))

    def __ge__(self, obj) -> Condition:
        return ~(self.__lt__(obj))

    def __add__(self, obj: Union[Any, Expression]) -> 'ColumnExpr':
        if isinstance(obj, Expression):
            obj_expr, obj_values = obj.as_tuple()
            return ColumnExpr(
                sql.SQL("({} + {})").format(self.expr, obj_expr),
                (*self.values, *obj_values)
            )
        else:
            return ColumnExpr(
                sql.SQL("({} + {})").format(self.expr, sql.Placeholder()),
                (*self.values, obj)
            )

    def __sub__(self, obj) -> 'ColumnExpr':
        if isinstance(obj, Expression):
            obj_expr, obj_values = obj.as_tuple()
            return ColumnExpr(
                sql.SQL("({} - {})").format(self.expr, obj_expr),
                (*self.values, *obj_values)
            )
        else:
            return ColumnExpr(
                sql.SQL("({} - {})").format(self.expr, sql.Placeholder()),
                (*self.values, obj)
            )

    def __mul__(self, obj) -> 'ColumnExpr':
        if isinstance(obj, Expression):
            obj_expr, obj_values = obj.as_tuple()
            return ColumnExpr(
                sql.SQL("({} * {})").format(self.expr, obj_expr),
                (*self.values, *obj_values)
            )
        else:
            return ColumnExpr(
                sql.SQL("({} * {})").format(self.expr, sql.Placeholder()),
                (*self.values, obj)
            )

    def CAST(self, target_type: sql.Composable):
        return ColumnExpr(
            sql.SQL("({}::{})").format(self.expr, target_type),
            self.values
        )


T = TypeVar('T')

if TYPE_CHECKING:
    from .models import RowModel


class Column(ColumnExpr, Generic[T]):
    def __init__(self, name: Optional[str] = None,
                 primary: bool = False, references: Optional['Column'] = None,
                 type: Optional[Type[T]] = None):
        self.primary = primary
        self.references = references
        self.name: str = name  # type: ignore
        self.owner: Optional['RowModel'] = None
        self._type = type

        self.expr = sql.Identifier(name) if name else sql.SQL('')
        self.values = ()

    def __set_name__(self, owner, name):
        # Only allow setting the owner once
        self.name = self.name or name
        self.owner = owner
        self.expr = sql.Identifier(self.owner._schema_, self.owner._tablename_, self.name)

    @overload
    def __get__(self: 'Column[T]', obj: None, objtype: "None | Type['RowModel']") -> 'Column[T]':
        ...

    @overload
    def __get__(self: 'Column[T]', obj: 'RowModel', objtype: Type['RowModel']) -> T:
        ...

    def __get__(self: 'Column[T]', obj: "RowModel | None", objtype: "Type[RowModel] | None" = None) -> "T | Column[T]":
        # Get value from row data or session
        if obj is None:
            return self
        else:
            return obj.data[self.name]


class Integer(Column[int]):
    pass


class String(Column[str]):
    pass


class Bool(Column[bool]):
    pass


class Timestamp(Column[datetime]):
    pass
