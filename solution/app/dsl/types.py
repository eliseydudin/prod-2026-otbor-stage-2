from typing import Optional, Self

from pydantic import BaseModel


class Span(BaseModel):
    "Position of a token in the source text"

    symbol: int


class ParserError(Exception):
    def __init__(
        self,
        detail: Optional[str] = None,
        position: Optional[Span] = None,
        exceptions: Optional[list[Self]] = None,
    ) -> None:
        super().__init__()
        self.detail = detail
        self.position = position
        self.exceptions = exceptions

    def flatten(self) -> list[Self]:
        errors = [self]
        if self.exceptions is not None:
            errors += self.exceptions

        return errors

    def add(self, next: Self):
        if self.exceptions is None:
            self.exceptions = [next]
        else:
            self.exceptions.append(next)
