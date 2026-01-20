import logging
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Optional

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


error_logger = logging.Logger("", level=logging.ERROR)


class AppError(BaseSchema, Exception):
    code: ErrorCode
    message: str
    status_code: int
    path: Optional[str] = None
    details: Optional[Any] = None

    def into_api_error(self) -> APIError:
        return APIError.model_validate(self)

    @staticmethod
    def make_internal_server_error(original_error: Exception):
        """
        Makes a 500 (internal server error) to respond to the user with. Immediately logs
        the underlying exception.
        """

        error_logger.error(f"A server error occured: {original_error}")

        return AppError(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            message="Произошла ошибка на сервере! Подробная информация об ошибке находится в логах",
        )
