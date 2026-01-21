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


def parse_rule(rule: str) -> Expr:
    stream = TokenStream(rule)
    parser = Parser(stream)
    return parser.expression()


def try_normalize(rule: str) -> str | list[ParserError]:
    try:
        expr = parse_rule(rule)

        return build_normalized_expression(expr)

    except ParserError as e:
        return [e]
