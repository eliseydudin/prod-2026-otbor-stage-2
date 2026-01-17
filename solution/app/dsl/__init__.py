import json

from .ast import And, Comp, Expr, ExprBase, Field, Operator, Or, Unary, Value
from .parser import Parser
from .token import Span, Token, TokenRepr, TokenStream
from .types import ParserError

__all__ = [
    "Expr",
    "Or",
    "And",
    "Unary",
    "Comp",
    "Value",
    "Operator",
    "Field",
    "ExprBase",
    "Token",
    "TokenRepr",
    "TokenStream",
    "Parser",
    "Span",
    "ParserError",
]


def try_jsonify_rule(rule: str) -> str:
    "Convert a DSL rule into JSON that can be stored inside the database."
    stream = TokenStream(rule)
    parser = Parser(stream)
    expr = parser.expression()
    return json.dumps(expr.to_json())
