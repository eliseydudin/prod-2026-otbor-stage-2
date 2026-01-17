from typing import Optional

from . import (
    And,
    Comp,
    Expr,
    Field,
    Operator,
    Or,
    Token,
    TokenRepr,
    TokenStream,
    Unary,
    Value,
)


class ParserError(Exception): ...


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
        self.positon += 1
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

    def take_value(self) -> Value:
        tok = self.advance()
        if tok is not None:
            if tok.repr == TokenRepr.STRING:
                return tok.data
            elif tok.repr == TokenRepr.NUMBER:
                return float(tok.data)

        raise ParserError()

    def take_field(self) -> Field:
        tok = self.advance()

        try:
            if tok is not None and tok.repr == TokenRepr.IDENTIFIER:
                return Field(tok.data)
        except ValueError:
            pass

        raise ParserError()

    def take_operator(self) -> Operator: ...

    def take_comp(self) -> Comp:
        field = self.take_field()
        operator = self.take_operator()
        value = self.take_value()

        return Comp(
            field=field,
            operator=operator,
            value=value,
        )

    def expression(self) -> Expr:
        left = self.term()
        if self.consume(TokenRepr.OR):
            right = self.term()
            return Or(left=left, right=right)

        return left

    def term(self) -> Expr:
        left = self.factor()
        if self.consume(TokenRepr.AND):
            right = self.factor()
            return And(left=left, right=right)

        return left

    def factor(self) -> Expr:
        if self.consume(TokenRepr.NOT):
            return Unary(inner=self.factor())
        elif self.consume(TokenRepr.LPAREN):
            expr = self.expression()
            self.consume(TokenRepr.RPAREN)
            return expr

        try:
            comp = self.take_comp()
            return comp
        except ParserError:
            raise ParserError()
