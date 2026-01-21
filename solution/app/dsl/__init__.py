from .ast import Expr, Field, Operator, Value, build_normalized_expression
from .parser import Parser
from .token import Span, Token, TokenRepr, TokenStream
from .types import ParserError

__all__ = [
    "Expr",
    "Value",
    "Operator",
    "Field",
    "Token",
    "TokenRepr",
    "TokenStream",
    "Parser",
    "Span",
    "ParserError",
]


def try_normalize(rule: str) -> str | list[ParserError]:
    try:
        stream = TokenStream(rule)
        parser = Parser(stream)
        expr = parser.expression()

        return build_normalized_expression(expr)

    except ParserError as e:
        return [e]
