from enum import IntEnum
from typing import Optional

from pydantic import BaseModel

from .types import ParserError, Span


class TokenRepr(IntEnum):
    LPAREN = 1
    RPAREN = 2
    AND = 3
    OR = 4
    NOT = 5
    STRING = 6
    FLOAT = 7
    INT = 8
    IDENTIFIER = 9

    GT = 10
    LT = 11
    LE = 12
    GE = 13
    EQ = 14
    NE = 15


class Token(BaseModel):
    repr: TokenRepr
    data: str
    span: Span

    def _make_keyword(self):
        if self.repr != TokenRepr.IDENTIFIER:
            return

        match self.data.lower():
            case "not":
                self.repr = TokenRepr.NOT
            case "and":
                self.repr = TokenRepr.AND
            case "or":
                self.repr = TokenRepr.OR


class TokenStream:
    def __init__(self, source: str) -> None:
        self.source = source
        self.position = 0

    def advance(self) -> Optional[str]:
        "Get the next character in the source string"
        try:
            ch = self.source[self.position]
            self.position += 1

            return ch

        except IndexError:
            return None

    def rewind(self):
        if self.position > 0:
            self.position -= 1

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
            span=Span(symbol=str_start),
        )

    def _number(self) -> Token:
        str_start = self.position - 1
        caught_dot = False

        while next := self.advance():
            if next.isnumeric():
                continue
            elif next == ".":
                if caught_dot:
                    raise ParserError(
                        "double dot found while parsing a number",
                        Span(symbol=self.position),
                    )
                else:
                    caught_dot = True
                continue

            self.rewind()
            break

        repr = TokenRepr.FLOAT if caught_dot else TokenRepr.INT

        return Token(
            repr=repr,
            data=self.source[str_start : self.position],
            span=Span(symbol=str_start),
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
            span=Span(symbol=start - 1),
        )

    def peek(self, s: str) -> bool:
        try:
            c = self.source[self.position + 1]
            return c == s
        except IndexError:
            return False

    def _fallback(self, start: str) -> Token:
        span = Span(symbol=self.position - 1)

        match start:
            case "=":
                return Token(span=span, repr=TokenRepr.EQ, data="=")
            case "!":
                if self.source[self.position] == "=":
                    self.advance()
                    return Token(span=span, repr=TokenRepr.NE, data="!=")

                raise ParserError(
                    "no such token that starts with `!` and doesn't end with `=`", span
                )
            case ">":
                if self.peek("="):
                    self.advance()
                    return Token(span=span, repr=TokenRepr.GE, data=">=")
                return Token(span=span, repr=TokenRepr.GT, data=">")
            case "<":
                if self.peek("="):
                    self.advance()
                    return Token(span=span, repr=TokenRepr.LE, data="<=")
                return Token(span=span, repr=TokenRepr.LT, data="<")
            case "(":
                return Token(span=span, repr=TokenRepr.LPAREN, data="(")
            case ")":
                return Token(span=span, repr=TokenRepr.RPAREN, data=")")

        raise ParserError("unknown token start")

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

            tok._make_keyword()
            yield tok
