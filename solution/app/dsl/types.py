from typing import Optional

from pydantic import BaseModel


class Span(BaseModel):
    "Position of a token in the source text"

    symbol: int


class ParserError(Exception):
    def __init__(
        self, detail: str | None | Exception = None, position: Optional[Span] = None
    ) -> None:
        super().__init__()
        self.detail = detail
        self.position = position

    def __str__(self) -> str:
        return f"{self.detail} at {self.position}"
