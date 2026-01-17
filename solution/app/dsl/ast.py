from enum import StrEnum
from typing import Any

from pydantic import BaseModel

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


class ExprBase(BaseModel):
    span: Span

    def to_json(self) -> dict[str, Any]:
        raise RuntimeError(
            "`to_json` is supposed to be called on classes inheriting `ExprBase`"
        )


class Comp(ExprBase):
    field: Field
    operator: Operator
    value: Value

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "comp",
            "field": self.field.value,
            "operator": self.operator.value,
            "value": self.value,
        }


class Unary(ExprBase):
    inner: ExprBase

    def to_json(self) -> dict[str, Any]:
        return {"type": "unary", "inner": self.inner.to_json()}


class And(ExprBase):
    left: ExprBase
    right: ExprBase

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "and",
            "left": self.left.to_json(),
            "right": self.right.to_json(),
        }


class Or(ExprBase):
    left: ExprBase
    right: ExprBase

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "or",
            "left": self.left.to_json(),
            "right": self.right.to_json(),
        }


type Expr = Or | And | Unary | Comp
