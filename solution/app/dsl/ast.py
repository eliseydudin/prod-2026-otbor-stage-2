from enum import StrEnum

from .types import Span

type Value = str | float


class Operator(StrEnum):
    GT = ">"
    LT = "<"
    LE = "<="
    GE = ">="
    EQ = "="
    NE = "!="


class Field(StrEnum):
    AMOUNT = "amount"
    CURRENCY = "currency"
    MERCHANT_ID = "merchantId"
    IP_ADDRESS = "ipAddress"
    DEVICE_ID = "deviceId"
    USER_AGE = "user.age"
    USER_REGION = "user.region"


class Or[T]:
    def __init__(self, left: T, right: T, span: Span) -> None:
        self.left = left
        self.right = right
        self.span = span


class And[T]:
    def __init__(self, left: T, right: T, span: Span) -> None:
        self.left = left
        self.right = right
        self.span = span


class Not[T]:
    def __init__(self, inner: T, span: Span) -> None:
        self.inner = inner
        self.span = span


class Comp:
    def __init__(
        self, field: Field, operator: Operator, value: Value, span: Span
    ) -> None:
        self.field = field
        self.operator = operator
        self.value = value
        self.span = span

    def validate_operation(self):
        if self.field in [Field.AMOUNT, Field.MERCHANT_ID, Field.USER_AGE]:
            assert isinstance(self.value, float)
        else:
            assert self.operator in [Operator.EQ, Operator.NE]
            assert isinstance(self.value, str)


type Expr = And[Expr] | Or[Expr] | Not[Expr] | Comp


def build_normalized_expression(expr: Expr) -> str:
    match expr:
        case And():
            left = build_normalized_expression(expr.left)
            if isinstance(expr.left, Or):
                left = f"({left})"

            right = build_normalized_expression(expr.right)
            if isinstance(expr.right, Or):
                right = f"({right})"

            return f"{left} AND {right}"

        case Or():
            left = build_normalized_expression(expr.left)
            right = build_normalized_expression(expr.right)
            return f"{left} OR {right}"

        case Not():
            return "NOT (" + build_normalized_expression(expr.inner) + ")"
        case Comp():
            val = expr.value
            if isinstance(val, str):
                val = "'" + val + "'"
            else:
                val = str(val)

            return f"{expr.field} {expr.operator} {val}"
