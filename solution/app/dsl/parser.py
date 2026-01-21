from typing import Optional

from .ast import And, Comp, Expr, Field, Not, Operator, Or, Span, Value
from .token import Token, TokenRepr, TokenStream
from .types import ParserError


class Parser:
    def __init__(self, stream: TokenStream) -> None:
        try:
            self.stream = list(iter(stream))
        except ParserError:
            self.stream: list[Token] = []
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

        raise ParserError(f"expected a field found {None if tok is None else tok.repr}")

    def take_operator(self) -> Operator:
        if tok := self.advance():
            for name, val in Operator.__members__.items():
                if tok.repr.name == name:
                    return val

        raise ParserError(
            f"expected an operator found {None if tok is None else tok.repr}",
        )

    def take_comp(self) -> Comp:
        try:
            field, span = self.take_field()
            operator = self.take_operator()
            value, _ = self.take_value()
        except ParserError as e:
            raise ParserError(f"while parsing comparison: {e}\n")

        return Comp(field, operator, value, span)

    def expression(self) -> Expr:
        left = self.term()

        if self.consume(TokenRepr.OR):
            right = self.term()
            return Or(left, right, left.span)

        return left

    def term(self) -> Expr:
        left = self.factor()

        if self.consume(TokenRepr.AND):
            right = self.factor()
            return And(left, right, left.span)

        return left

    def factor(self) -> Expr:
        if tok := self.consume(TokenRepr.NOT):
            return Not(self.factor(), tok.span)

        elif self.consume(TokenRepr.LPAREN):
            expr = self.expression()
            self.consume(TokenRepr.RPAREN)
            return expr

        try:
            comp = self.take_comp()
            return comp
        except ParserError:
            raise ParserError("expected `NOT`, `(`, `)` or a comparison expression")


# stream = TokenStream("user.age > 10 OR user.age = 'RU-MOW' AND amount > 20.51025")
# parser = Parser(stream)
# print(parser.expression().to_json())
