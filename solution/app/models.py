import uuid
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Optional

import pydantic as pd
from pydantic import BaseModel, ConfigDict, EmailStr  # , model_validator
from pydantic.alias_generators import to_camel

# from pydantic_extra_types.coordinate import Latitude, Longitude
# from pydantic_extra_types.country import CountryAlpha2
# from pydantic_extra_types.currency_code import Currency
from sqlmodel import Field, SQLModel

from app.dsl.types import ParserError


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class Role(StrEnum):
    ADMIN = "ADMIN"
    USER = "USER"

    def is_admin(self) -> bool:
        return self == Role.ADMIN


class Gender(StrEnum):
    MALE = "MALE"
    FEMALE = "FEMALE"


class MaritalStatus(StrEnum):
    SINGLE = "SINGLE"
    MARRIED = "MARRIED"
    DIVORCED = "DIVORCED"
    WIDOWED = "WIDOWED"


class UserBase(SQLModel):
    email: EmailStr = Field(max_length=254, unique=True)
    full_name: str = Field(serialization_alias="fullName", min_length=2, max_length=200)
    role: Role = Role.USER
    is_active: bool = Field(default=True, serialization_alias="isActive")

    region: Optional[str] = Field(default=None, max_length=32)
    gender: Optional[Gender] = Field(default=None)
    age: Optional[int] = Field(default=None, ge=18, le=120)
    marital_status: Optional[MaritalStatus] = Field(
        default=None, serialization_alias="maritalStatus"
    )


class UserDB(UserBase, table=True):
    __tablename__ = "user"  # type: ignore
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    password: str  # always hashed


class User(UserBase):
    id: str
    created_at: str = Field(serialization_alias="createdAt")
    updated_at: str = Field(serialization_alias="updatedAt")

    @staticmethod
    def from_db_user(user: UserDB):
        base = UserBase.model_validate(user).model_dump()
        return User.model_validate(
            {
                "id": str(user.id),
                "created_at": str(user.created_at),
                "updated_at": str(user.updated_at),
                **base,
            }
        )


class Token(BaseSchema):
    sub: uuid.UUID
    role: Role
    iat: datetime  # created at
    exp: datetime  # expiration time

    @staticmethod
    def from_user(user: UserDB):
        time = datetime.now(timezone.utc)
        return Token(
            sub=user.id, role=user.role, iat=time, exp=time + timedelta(hours=1)
        )

    def to_dict(self):
        return {
            "sub": str(self.sub),
            "role": self.role.value,
            "iat": int(self.iat.timestamp()),
            "exp": int(self.exp.timestamp()),
        }


class OAuth2Token(BaseModel):
    access_token: str
    token_type: str


class RegisterRequest(BaseSchema):
    model_config = pd.ConfigDict(regex_engine="python-re")

    email: EmailStr = pd.Field(max_length=254)
    password: str = pd.Field(
        min_length=8,
        max_length=72,
        pattern=r"^(?=.*[A-Za-z])(?=.*\d).+$",
    )
    full_name: str = pd.Field(min_length=2, max_length=200)
    region: Optional[str] = pd.Field(default=None, max_length=32)
    gender: Optional[Gender] = None
    age: Optional[int] = pd.Field(default=None, ge=18, le=120)
    marital_status: Optional[MaritalStatus] = None


class UserCreateRequest(RegisterRequest):
    role: Role


class UserUpdateRequest(BaseSchema):
    full_name: str = pd.Field(min_length=2, max_length=200)
    region: Optional[str] = pd.Field(max_length=32)
    gender: Optional[Gender]
    age: Optional[int] = pd.Field(ge=18, le=120)
    marital_status: Optional[MaritalStatus] = None

    role: Optional[Role] = None
    is_active: Optional[bool] = Field(default=None)


class LoginRequest(BaseSchema):
    model_config = pd.ConfigDict(regex_engine="python-re")

    email: str = pd.Field(max_length=254)
    password: str = pd.Field(
        min_length=8, max_length=72, pattern=r"^(?=.*[A-Za-z])(?=.*\d).+$"
    )


class FraudRuleBase(SQLModel):
    name: str = Field(min_length=3, max_length=120)
    dsl_expression: str = Field(
        min_length=3,
        max_length=2000,
        serialization_alias="dslExpression",
    )

    enabled: bool = Field(default=True)
    priority: int = Field(ge=1, default=100)
    description: Optional[str] = Field(max_length=500, default=None)


class FraudRuleUpdateRequest(FraudRuleBase):
    dsl_expression: str = Field(
        min_length=3,
        max_length=2000,
        alias="dslExpression",
    )


class FraudRuleCreateRequest(FraudRuleBase):
    dsl_expression: str = Field(
        min_length=3,
        max_length=2000,
        alias="dslExpression",
    )


class FraudRuleDB(FraudRuleBase, table=True):
    __tablename__ = "fraud_rule"  # type: ignore
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    dsl_expression_json: str  # dsl_expression stored in json


class FraudRule(FraudRuleBase):
    id: str
    created_at: str = Field(serialization_alias="createdAt")
    updated_at: str = Field(serialization_alias="updatedAt")

    @staticmethod
    def from_db_rule(rule: FraudRuleDB):
        base = FraudRuleBase.model_validate(rule).model_dump()
        return FraudRule.model_validate(
            {
                "id": str(rule.id),
                "created_at": str(rule.created_at),
                "updated_at": str(rule.updated_at),
                **base,
            }
        )


class DslValidateRequest(BaseSchema):
    dsl_expression: str = Field(min_length=3, max_length=200)


class DslError(BaseSchema):
    code: str
    message: str
    position: Optional[int] = None
    near: Optional[str] = None

    @staticmethod
    def from_parser_error(err: ParserError):
        return DslError(
            code="DSL_PARSE_ERROR",
            message=str(err),
        )


class DslValidateResponse(BaseSchema):
    is_valid: bool
    errors: list[DslError]

    normalized_expression: Optional[str] = None


class PagedUsers(BaseSchema):
    items: list[User]
    total: int = pd.Field(ge=0)
    page: int = pd.Field(ge=0)
    size: int = pd.Field(ge=1)
