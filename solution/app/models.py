import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from ipaddress import IPv4Address
from typing import Annotated, Any, Optional

import pydantic as pd
from pydantic import BaseModel, ConfigDict, EmailStr, model_validator
from pydantic.alias_generators import to_camel
from pydantic_extra_types.coordinate import Latitude, Longitude
from pydantic_extra_types.country import CountryAlpha2
from pydantic_extra_types.currency_code import Currency
from sqlmodel import JSON, Column, Field, SQLModel

from app.dsl.types import EvaluationRequest, ParserError


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

    def is_user(self) -> bool:
        return self == Role.USER


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
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        serialization_alias="createdAt",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        serialization_alias="updatedAt",
    )


class UserDB(UserBase, table=True):
    __tablename__ = "user"  # type: ignore
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    password: str  # always hashed


class User(UserBase):
    id: str

    @staticmethod
    def from_db_user(user: UserDB):
        base = UserBase.model_validate(user).model_dump()
        return User.model_validate(
            {
                "id": str(user.id),
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
        time = datetime.now(UTC)
        return Token(
            sub=user.id,
            role=user.role,
            iat=time,
            exp=time + timedelta(hours=1),
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
        min_length=8,
        max_length=72,
        pattern=r"^(?=.*[A-Za-z])(?=.*\d).+$",
    )


class FraudRuleBase(SQLModel):
    name: str = Field(min_length=3, max_length=120, unique=True)
    dsl_expression: str = Field(
        min_length=3,
        max_length=2000,
        serialization_alias="dslExpression",
    )

    enabled: bool = Field(default=True)
    priority: int = Field(ge=1, default=100)
    description: Optional[str] = Field(max_length=500, default=None)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        serialization_alias="createdAt",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        serialization_alias="updatedAt",
    )


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


class FraudRule(FraudRuleBase):
    id: str

    @staticmethod
    def from_db_rule(rule: FraudRuleDB):
        base = FraudRuleBase.model_validate(rule).model_dump()
        return FraudRule.model_validate(
            {
                "id": str(rule.id),
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
            message="<none>" if err.detail is None else err.detail,
            position=err.position.symbol if err.position is not None else None,
        )


class DslValidateResponse(BaseSchema):
    is_valid: bool
    errors: list[DslError]

    normalized_expression: Optional[str] = None


class TransactionLocation(BaseSchema):
    country: Optional[CountryAlpha2] = None
    city: Optional[str] = pd.Field(max_length=128, default=None)
    latitude: Optional[Latitude] = None
    longitude: Optional[Longitude] = None

    @model_validator(mode="after")
    def _validate(self):
        if (self.latitude is None and self.longitude is not None) or (
            self.latitude is not None and self.longitude is None
        ):
            raise ValueError("latitude and longitude depend on eachother")
        return self


class TransactionStatus(StrEnum):
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"

    def is_declined(self) -> bool:
        return self == TransactionStatus.DECLINED

    def is_approved(self) -> bool:
        return self == TransactionStatus.APPROVED


class TransactionChannel(StrEnum):
    WEB = "WEB"
    MOBILE = "MOBILE"
    POS = "POS"
    OTHER = "OTHER"


class PagedUsers(BaseSchema):
    items: list[User]
    total: int = pd.Field(ge=0)
    page: int = pd.Field(ge=0)
    size: int = pd.Field(ge=1)


MccCode = Annotated[str, pd.Field(pattern=r"^\d{4}$")]


class TransactionCreateRequest(BaseSchema):
    user_id: uuid.UUID
    amount: float = pd.Field(le=999999999.99, ge=0.01)
    currency: Currency
    timestamp: datetime

    merchant_id: Optional[str] = pd.Field(max_length=64, default=None)
    merchant_category_code: Optional[MccCode] = None
    ip_address: Optional[IPv4Address] = None
    device_id: Optional[str] = pd.Field(max_length=128, default=None)
    channel: Optional[TransactionChannel] = None
    location: Optional[TransactionLocation] = None
    metadata: Optional[Any] = None


class Transaction(TransactionCreateRequest):
    id: uuid.UUID = pd.Field(default_factory=uuid.uuid4)
    created_at: datetime = pd.Field(default_factory=lambda: datetime.now(UTC))
    is_fraud: bool
    status: TransactionStatus


class FraudRuleEvaluationResult(BaseSchema):
    rule_id: uuid.UUID
    rule_name: str
    priority: int
    matched: bool
    description: Optional[str] = None

    class Config:
        validate_assignment = True


class TransactionDB(SQLModel, table=True):
    __tablename__ = "transaction"  # type: ignore
    id: uuid.UUID = Field(primary_key=True)

    user_id: uuid.UUID = Field(foreign_key="user.id")
    currency: str
    status: TransactionStatus
    timestamp: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_fraud: bool
    amount: float

    merchant_id: Optional[str] = None
    merchant_category_code: Optional[str] = None
    ip_address: Optional[str] = None
    device_id: Optional[str] = None
    channel: Optional[TransactionChannel] = None
    location: Optional[TransactionLocation] = Field(sa_column=Column(JSON))
    meta_data: Optional[Any] = Field(
        sa_column=Column("metadata", JSON),
        default=None,
        schema_extra={"deserialization_alias": "metadata"},
    )

    rule_results: list[FraudRuleEvaluationResult] = Field(
        sa_column=Column("rule_results", JSON)
    )

    def to_transaction(self) -> Transaction:
        return Transaction(
            **self.model_dump(exclude={"meta_data", "metadata"}),
            metadata=self.meta_data,
        )


class TransactionDecision(BaseSchema):
    transaction: Transaction
    rule_results: list[FraudRuleEvaluationResult]


def make_eval_request(transaction: Transaction | TransactionDB, user: UserBase):
    return EvaluationRequest(
        amount=transaction.amount,
        currency=transaction.currency,
        user_age=user.age,
        merchant_id=transaction.merchant_id,
        ip_address=(
            None if transaction.ip_address is None else str(transaction.ip_address)
        ),
        device_id=transaction.device_id,
        user_region=user.region,
    )


class PagedTransactions(BaseSchema):
    items: list[Transaction]
    total: int = pd.Field(ge=0)
    page: int = pd.Field(ge=0)
    size: int = pd.Field(ge=1)


class TransactionCreateBatch(BaseSchema):
    items: list[Any]


class TransactionBatchResultItem(BaseSchema):
    index: int
    decision: Optional[TransactionDecision] = None
    error: Optional[Any] = None


class TransactionBatchResponse(BaseSchema):
    items: list[TransactionBatchResultItem]


class MerchantRiskRow(BaseSchema):
    merchant_id: str
    merchant_category_code: Optional[MccCode] = None
    tx_count: int
    gmv: float
    decline_rate: float

    @staticmethod
    def from_merchant_data(merchant_id: str, mcc: Optional[MccCode]):
        return MerchantRiskRow(
            merchant_id=merchant_id,
            merchant_category_code=mcc,
            tx_count=0,
            gmv=0.0,
            decline_rate=0.0,
        )


class TransactionsAnalysisResult(BaseSchema):
    transaction_count: int = 0
    approved: int = 0
    gmv: float = 0.0
    merchants: list[MerchantRiskRow]


class StatsOverview(BaseSchema):
    from_time: datetime = pd.Field(serialization_alias="from")
    to: datetime
    volume: int
    gmv: float

    approval_rate: float
    decline_rate: float
    top_risk_merchants: list[MerchantRiskRow]


class RuleMatchRow(BaseSchema):
    rule_id: uuid.UUID
    rule_name: str
    matches: int
    unique_users: int
    unique_merchants: int
    share_of_declines: float


class RuleMatchRowStat(BaseSchema):
    rule_id: uuid.UUID
    rule_name: str
    matches: int = 0
    users_affected: set[uuid.UUID] = set()
    merchants_affected: set[str] = set()
    declines: int = 0

    def into_rule_match_row(self, all_declines: int) -> RuleMatchRow:
        return RuleMatchRow(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            matches=self.matches,
            unique_merchants=len(self.merchants_affected),
            unique_users=len(self.users_affected),
            share_of_declines=(
                0.0 if all_declines == 0 else round(self.declines / all_declines, 2)
            ),
        )

    @staticmethod
    def from_rule_eval_result(res: FraudRuleEvaluationResult):
        return RuleMatchRowStat(rule_id=res.rule_id, rule_name=res.rule_name)


class RuleMatchStats(BaseSchema):
    items: list[RuleMatchRow]


class MerchantRiskStats(BaseSchema):
    items: list[MerchantRiskRow]


class UserStats(BaseModel):
    user_id: uuid.UUID = Field(serialization_alias="userId")
    tx_count_24h: int = Field(serialization_alias="txCount_24h")
    gmv_24h: float
    distinct_devices_24h: int = Field(serialization_alias="distinctDevices_24h")
    distinct_ips_24h: int = Field(serialization_alias="distinctIps_24h")
    distinct_cities_24h: int = Field(serialization_alias="distinctCities_24h")
    decline_rate_30d: float = Field(serialization_alias="declineRate_30d")
    last_seen_at: Optional[datetime] = Field(
        serialization_alias="lastSeenAt",
        default=None,
    )
