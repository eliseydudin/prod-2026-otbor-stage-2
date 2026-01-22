import uuid
from datetime import datetime
from enum import StrEnum
from logging import getLogger
from typing import Any, Optional, Sequence

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field

from app.models import BaseSchema


class ErrorCode(StrEnum):
    BAD_REQUEST = "BAD_REQUEST"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    EMAIL_ALREADY_EXISTS = "EMAIL_ALREADY_EXISTS"
    USER_INACTIVE = "USER_INACTIVE"
    DSL_PARSE_ERROR = "DSL_PARSE_ERROR"
    DSL_INVALID_FIELD = "DSL_INVALID_FIELD"
    DSL_INVALID_OPERATOR = "DSL_INVALID_OPERATOR"
    RULE_NAME_ALREADY_EXISTS = "RULE_NAME_ALREADY_EXISTS"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"


class APIError(BaseSchema):
    code: ErrorCode
    message: str
    trace_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    timestamp: datetime = Field(default_factory=datetime.now)
    path: str
    details: Optional[Any] = None

    def stringify(self) -> str:
        return (
            f"ID={self.trace_id} CODE={self.code.value} at {self.path}: {self.message}"
        )


logger = getLogger("app")


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int,
        path: Optional[str] = None,
        details: Optional[Any] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.path = path
        self.details = details
        self.headers = headers

    def into_api_error(self) -> APIError:
        return APIError.model_validate(self.__dict__)

    @staticmethod
    def make_internal_server_error(original_error: Exception | str):
        logger.error(f"an error occured: {original_error}")
        return AppError(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            message="Произошла ошибка на сервере! Подробная информация находится в логах",
        )

    @staticmethod
    def make_not_found_error(message: str, details: Optional[dict[str, Any]] = None):
        return AppError(
            code=ErrorCode.NOT_FOUND, message=message, status_code=404, details=details
        )

    @staticmethod
    def make_forbidden_error():
        return AppError(
            code=ErrorCode.FORBIDDEN,
            message="Недостаточно прав для выполнения операции",
            status_code=403,
        )

    @staticmethod
    def make_email_already_exists_error():
        return AppError(
            code=ErrorCode.EMAIL_ALREADY_EXISTS,
            status_code=409,
            message="Пользователь с таким email уже существует",
        )

    @staticmethod
    def make_invalid_data_error(message: str):
        return AppError(
            code=ErrorCode.VALIDATION_FAILED,
            message=message,
            status_code=422,
        )

    @staticmethod
    def make_rule_name_already_exists():
        return AppError(
            code=ErrorCode.RULE_NAME_ALREADY_EXISTS,
            status_code=409,
            message="Уже существует правило с таким названием.",
        )


PYDANTIC_ERROR_FIELDS = ["decimal", "constrained-float"]


def _stringify_field_details(details: tuple[str | int, ...]):
    result = ""

    for item in details:
        if item in PYDANTIC_ERROR_FIELDS:
            continue

        if isinstance(item, str):
            result += item + "."
        else:
            result = result.rstrip(".") + f"[{item}]."

    return result.rstrip(".")


class FieldError(BaseSchema):
    field: str
    issue: str
    rejected_value: Optional[Any] = None

    @staticmethod
    def from_field_details(data: Any):
        return FieldError(
            field=_stringify_field_details(data["loc"][1:]),
            issue=data["msg"],
            rejected_value=data["input"],
        )


def normalize_field_errors(errors: Sequence[Any]) -> list[FieldError]:
    return list(map(FieldError.from_field_details, errors))


def normalize_validation_error_to_dict(
    request: Request, error: RequestValidationError
) -> tuple[int, dict]:
    path = request.url.path.rstrip("/")

    # a bit hacky but its fastapi's devs fault that `RequestValidationError` is
    # basically untyped
    if error.errors()[0]["type"] == "json_invalid":
        return 400, {
            "code": ErrorCode.BAD_REQUEST,
            "message": "Невалидный JSON",
            "traceId": uuid.uuid4(),
            "timestamp": datetime.now(),
            "path": path,
            "details": {"hint": "Проверьте запятые/кавычки"},
        }

    return 422, {
        "code": ErrorCode.VALIDATION_FAILED,
        "message": "Некоторые поля не прошли валидацию",
        "traceId": uuid.uuid4(),
        "timestamp": datetime.now(),
        "path": path,
        "fieldErrors": normalize_field_errors(error.errors()),
    }


def normalize_validation_error(request: Request, error: RequestValidationError):
    status, d = normalize_validation_error_to_dict(request, error)
    return JSONResponse(status_code=status, content=jsonable_encoder(d))


class TimeValidationError(Exception):
    def __init__(self, from_time: datetime, to: datetime) -> None:
        self.from_time = from_time
        self.to = to

    def into_json_response(self, path: str) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(
                {
                    "code": ErrorCode.VALIDATION_FAILED,
                    "message": "Некоторые поля не прошли валидацию",
                    "traceId": uuid.uuid4(),
                    "timestamp": datetime.now(),
                    "path": path,
                    "fieldErrors": [
                        {
                            "field": "from",
                            "issue": "from is expected to be less than to",
                            "rejectedValue": self.from_time,
                        }
                    ],
                }
            ),
        )
