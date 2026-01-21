import uuid
from datetime import datetime
from enum import StrEnum
from logging import getLogger
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
    trace_id: uuid.UUID
    timestamp: datetime = Field(default_factory=datetime.now)
    path: str
    details: Optional[Any] = None


logger = getLogger("app")


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int,
        path: Optional[str] = None,
        details: Optional[Any] = None,
        trace_id: Optional[uuid.UUID] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.path = path
        self.details = details
        self.trace_id = trace_id
        self.headers = headers

    def into_api_error(self) -> APIError:
        if self.trace_id is None:
            self.trace_id = uuid.uuid4()

        return APIError.model_validate(self.__dict__)

    @staticmethod
    def make_internal_server_error(original_error: Exception):
        """
        Makes a 500 (internal server error) to respond to the user with. Immediately logs
        the underlying exception.
        """

        error_id = uuid.uuid4()
        logger.error(f"ID={error_id} an error occured: {original_error}")

        return AppError(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            message="Произошла ошибка на сервере! Подробная информация находится в логах",
            trace_id=error_id,
        )

    @staticmethod
    def make_not_found_error(message: str):
        return AppError(code=ErrorCode.NOT_FOUND, message=message, status_code=404)

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
