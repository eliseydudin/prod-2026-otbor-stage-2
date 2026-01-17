from typing import Optional

from .ast import (
    And,
    Comp,
    Expr,
    Field,
    Operator,
    Or,
    Span,
    Unary,
    Value,
)
from .token import Token, TokenRepr, TokenStream
from .types import ParserError


class Parser:
    def __init__(self, stream: TokenStream) -> None:
        self.stream = list(iter(stream))
        self.position = 0

    def get(self, position: int) -> Optional[Token]:
        try:
            return self.stream[position]
        except IndexError:
            return None

    def current(self) -> Optional[Token]:
        return self.get(self.position)

    def advance(self) -> Optional[Token]:
        self.position += 1
        return self.get(self.position - 1)

    def check(self, repr: TokenRepr):
        return self.check_many([repr])

    def check_many(self, reprs: list[TokenRepr]):
        if tok := self.current():
            if tok.repr in reprs:
                return tok

        return None

    def consume(self, repr: TokenRepr) -> Optional[Token]:
        if tok := self.check(repr):
            self.position += 1
            return tok

    def take_value(self) -> tuple[Value, Span]:
        tok = self.advance()
        if tok is not None:
            if tok.repr == TokenRepr.STRING:
                return tok.data, tok.span
            elif tok.repr == TokenRepr.NUMBER:
                return float(tok.data), tok.span

        raise ParserError()

    def take_field(self) -> tuple[Field, Span]:
        tok = self.advance()

        try:
            if tok is not None and tok.repr == TokenRepr.IDENTIFIER:
                return Field(tok.data), tok.span
        except ValueError:
            pass

        raise ParserError()

    def take_operator(self) -> Operator:
        if tok := self.advance():
            for name, val in Operator.__members__.items():
                if tok.repr.name == name:
                    return val

        raise ParserError()

    def take_comp(self) -> Comp:
        field, span = self.take_field()
        operator = self.take_operator()
        value, _ = self.take_value()

        return Comp(field=field, operator=operator, value=value, span=span)

    def expression(self) -> Expr:
        left = self.term()
        if self.consume(TokenRepr.OR):
            right = self.term()
            return Or(left=left, right=right, span=left.span)

        return left

    def term(self) -> Expr:
        left = self.factor()
        if self.consume(TokenRepr.AND):
            right = self.factor()
            return And(left=left, right=right, span=left.span)

        return left

    def factor(self) -> Expr:
        if tok := self.consume(TokenRepr.NOT):
            return Unary(inner=self.factor(), span=tok.span)
        elif self.consume(TokenRepr.LPAREN):
            expr = self.expression()
            self.consume(TokenRepr.RPAREN)
            return expr

        try:
            comp = self.take_comp()
            return comp
        except ParserError:
            raise ParserError()


# stream = TokenStream("(user.age > 10)")
# parser = Parser(stream)
# print(parser.expression().model_dump_json(indent=2))
