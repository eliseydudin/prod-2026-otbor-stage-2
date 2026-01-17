from enum import StrEnum

from pydantic import BaseModel

type Value = str | float


class Operator(StrEnum):
    GT = ">"
    LT = "<"
    LE = "<="
    GE = ">="
    EQ = "=="
    NE = "!="


class Field(StrEnum):
    AMOUNT = "amount"
    CURRENCY = "currency"
    MERCHANT_ID = "merchantId"
    IP_ADDRESS = "ipAddress"
    DEVICE_ID = "deviceId"
    USER_AGE = "user.age"
    USER_REGION = "user.region"


class ExprBase(BaseModel): ...


class Comp(ExprBase):
    field: Field
    operator: Operator
    value: Value


class Unary(ExprBase):
    inner: ExprBase


class And(ExprBase):
    left: ExprBase
    right: ExprBase


class Or(ExprBase):
    left: ExprBase
    right: ExprBase


type Expr = Or | And | Unary | Comp
