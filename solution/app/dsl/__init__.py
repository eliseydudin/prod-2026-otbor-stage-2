from .ast import Expr, Field, Operator, Value, build_normalized_expression
from .parser import Parser
from .token import Span, Token, TokenRepr, TokenStream
from .types import ParserError
from typing import Optional

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

    expr = parser.expression()
    if parser.stream_error is not None:
        raise parser.stream_error

    return expr


def try_normalize(rule: str) -> str | list[ParserError]:
    try:
        expr = parse_rule(rule)
        return build_normalized_expression(expr)

    except ParserError as e:
        return e.flatten()


def normalize_or_none(rule: str) -> Optional[str]:
    try:
        expr = parse_rule(rule)
        return build_normalized_expression(expr)

    except ParserError:
        return None


def is_valid(rule: str):
    try:
        _expr = parse_rule(rule)
        return True
    except Exception:
        return False


def evaluate(expr: Expr, request):
    return False
