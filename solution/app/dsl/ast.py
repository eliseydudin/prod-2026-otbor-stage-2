from enum import StrEnum

from .types import Span, EvaluationRequest

type Value = str | float | int


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

    def get_propery_on_request(self, req: EvaluationRequest):
        match self:
            case Field.AMOUNT:
                return req.amount
            case Field.CURRENCY:
                return req.currency
            case Field.MERCHANT_ID:
                return req.merchant_id
            case Field.DEVICE_ID:
                return req.device_id
            case Field.USER_AGE:
                return req.user_age
            case Field.USER_REGION:
                return req.user_region


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
            assert isinstance(self.value, float) or isinstance(self.value, int)
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


def eval_comp(comp: Comp, req: EvaluationRequest):
    val = comp.field.get_propery_on_request(req)
    if val is None:
        return False

    # type ignore is ok here because a valid expression is guaranteed
    # to have valid comparison operations
    match comp.operator:
        case Operator.GT:
            return val > comp.value  # type: ignore
        case Operator.GE:
            return val >= comp.value  # type: ignore
        case Operator.LT:
            return val < comp.value  # type: ignore
        case Operator.LE:
            return val <= comp.value  # type: ignore
        case Operator.EQ:
            return val == comp.value
        case Operator.NE:
            return val != comp.value


def evaluate(expr: Expr, request: EvaluationRequest) -> bool:
    match expr:
        case Or():
            return evaluate(expr.left, request) or evaluate(expr.right, request)
        case And():
            return evaluate(expr.left, request) and evaluate(expr.right, request)
        case Not():
            return not evaluate(expr.inner, request)
        case Comp():
            return eval_comp(expr, request)

    return False
