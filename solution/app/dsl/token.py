from enum import IntEnum
from typing import Optional

from pydantic import BaseModel


class TokenRepr(IntEnum):
    LPAREN = 1
    RPAREN = 2
    AND = 3
    OR = 4
    NOT = 5
    STRING = 6
    NUMBER = 7
    IDENTIFIER = 8

    GT = 9
    LT = 10
    LE = 11
    GE = 12
    EQ = 13
    NE = 14


class Span(BaseModel):
    "Position of a token in the source text"

    line: int
    symbol: int


class Token(BaseModel):
    repr: TokenRepr
    data: str
    span: Span


class TokenStream:
    def __init__(self, source: str) -> None:
        self.source = source
        self.position = 0
        self.current_span = Span(line=0, symbol=0)
        self.previous_span: Optional[Span] = None

    def advance(self) -> Optional[str]:
        "Get the next character in the source string"
        try:
            ch = self.source[self.position]
            self.previous_span = self.current_span

            if ch == "\n":
                self.current_span.line += 1
                self.current_span.symbol = 0
            else:
                self.current_span.symbol += 1
            self.position += 1

            return ch

        except IndexError:
            return None

    def rewind(self):
        "Try to return to the last position in the token stream"
        if self.position > 0 and self.previous_span is not None:
            self.position -= 1
            self.current_span = self.previous_span
            self.previous_span = None

    def skip_whitespace(self):
        while next := self.advance():
            if next.isspace():
                continue

            return next

    def _identifier(self) -> Token:
        str_start = self.position - 1

        while next := self.advance():
            if next.isalpha() or next == ".":
                continue
            self.rewind()
            break

        return Token(
            repr=TokenRepr.IDENTIFIER,
            data=self.source[str_start : self.position],
            span=self.current_span,
        )

    def _number(self) -> Token:
        str_start = self.position - 1
        caught_dot = False

        while next := self.advance():
            if next.isnumeric():
                continue
            elif next == ".":
                if caught_dot:
                    raise Exception("double dot!")
                else:
                    caught_dot = True
                continue

            self.rewind()
            break

        return Token(
            repr=TokenRepr.NUMBER,
            data=self.source[str_start : self.position],
            span=self.current_span,
        )

    def _string(self) -> Token:
        start = self.position

        while next := self.advance():
            if next != "'":
                continue
            break

        data = self.source[start : self.position - 1]

        return Token(
            repr=TokenRepr.STRING,
            data=data,
            span=self.current_span,
        )

    # TODO
    def _fallback(self, start: str) -> Token: ...

    def _next_token(self, start: str) -> Token:
        match start:
            case a if a.isalpha():
                return self._identifier()
            case n if n.isnumeric():
                return self._number()
            case "'":
                return self._string()

        return self._fallback(start)

    def __iter__(self):
        while next := self.skip_whitespace():
            tok = self._next_token(next)
            if tok is None:
                break

            yield tok
