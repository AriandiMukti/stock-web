"""
Recursive-descent parser: tokens -> AST.

Grammar (informal):

    program    := statement*
    statement  := 'stock' NAME
                | 'universe' ( 'all' | '[' NAME (',' NAME)* ']' )
                | 'param' NAME '=' expr               values to sweep, e.g. param n = [10, 20, 50]
                | 'fn' NAME '(' params ')' ( '=' expr | block )
                | 'if' expr block ( 'else' ( block | if-statement ) )?
                | 'return' expr
                | NAME '=' expr
                | expr
    block      := '{' statement* '}'
    expr       := or ;  or := and ('or' and)* ;  and := not ('and' not)*
    not        := 'not' not | compare
    compare    := sum (('<'|'>'|'<='|'>='|'=='|'!=') sum)?
    sum        := product (('+'|'-') product)*
    product    := unary (('*'|'/') unary)*
    unary      := '-' unary | postfix
    postfix    := atom ( '(' args ')' | '[' expr ']' )*
    args       := ( NAME '=' expr | expr ) (',' ...)*
    atom       := NUMBER | STRING | 'true' | 'false' | NAME | '(' expr ')'
                | '[' expr (',' expr)* ']'          a list, for options like days=[1, 5, 20]

`x[n]` means "x, n bars ago" (like Pine Script), not list indexing.
"""
from dataclasses import dataclass, field

from .errors import StockLangError
from .lexer import tokenize


# ---- AST nodes ------------------------------------------------------------

@dataclass
class Node:
    line: int = field(default=0, kw_only=True)
    col: int = field(default=0, kw_only=True)


@dataclass
class Num(Node):
    value: float


@dataclass
class Str(Node):
    value: str


@dataclass
class Bool(Node):
    value: bool


@dataclass
class Name(Node):
    name: str


@dataclass
class BinOp(Node):
    op: str
    left: Node
    right: Node


@dataclass
class UnaryOp(Node):
    op: str
    operand: Node


@dataclass
class Call(Node):
    func: str
    args: list
    kwargs: dict


@dataclass
class Lag(Node):
    target: Node
    bars: Node


@dataclass
class ListLit(Node):
    items: list


@dataclass
class Assign(Node):
    name: str
    value: Node


@dataclass
class StockStmt(Node):
    symbol: str


@dataclass
class UniverseStmt(Node):
    symbols: list      # None means "all stocks with data"


@dataclass
class ParamStmt(Node):
    name: str
    value: Node


@dataclass
class FnDef(Node):
    name: str
    params: list
    body: list


@dataclass
class If(Node):
    cond: Node
    then: list
    otherwise: list


@dataclass
class Return(Node):
    value: Node


@dataclass
class ExprStmt(Node):
    expr: Node


# ---- parser ---------------------------------------------------------------

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    # helpers
    @property
    def tok(self):
        return self.tokens[self.pos]

    def peek(self, offset=1):
        return self.tokens[min(self.pos + offset, len(self.tokens) - 1)]

    def at(self, kind, value=None):
        t = self.tok
        return t.kind == kind and (value is None or t.value == value)

    def advance(self):
        t = self.tok
        self.pos += 1
        return t

    def expect(self, kind, value=None, what=None):
        if not self.at(kind, value):
            t = self.tok
            wanted = what or (repr(value) if value else kind)
            got = 'end of line' if t.kind == 'nl' else 'end of file' if t.kind == 'eof' else repr(t.value)
            raise StockLangError(f"expected {wanted}, got {got}", t.line, t.col)
        return self.advance()

    def skip_newlines(self):
        while self.at('nl') or self.at('op', ';'):
            self.advance()

    def end_statement(self):
        if self.at('op', '}') or self.at('eof'):
            return
        if not (self.at('nl') or self.at('op', ';')):
            t = self.tok
            raise StockLangError(f"unexpected {t.value!r} after statement", t.line, t.col)
        self.skip_newlines()

    def pos_of(self, t):
        return {'line': t.line, 'col': t.col}

    # statements
    def parse_program(self):
        self.skip_newlines()
        stmts = []
        while not self.at('eof'):
            stmts.append(self.statement())
            self.end_statement()
        return stmts

    def block(self):
        self.expect('op', '{')
        self.skip_newlines()
        stmts = []
        while not self.at('op', '}'):
            if self.at('eof'):
                t = self.tok
                raise StockLangError("missing '}'", t.line, t.col)
            stmts.append(self.statement())
            self.end_statement()
        self.expect('op', '}')
        return stmts

    def statement(self):
        t = self.tok
        p = self.pos_of(t)

        if self.at('kw', 'stock'):
            self.advance()
            sym = self.expect('name', what='a stock code like BBCA')
            return StockStmt(sym.value.upper(), **p)

        if self.at('kw', 'universe'):
            self.advance()
            if self.at('name', 'all'):
                self.advance()
                return UniverseStmt(None, **p)
            self.expect('op', '[', what="'all' or a list like [BBCA, BBRI]")
            syms = [self.expect('name', what='a stock code').value.upper()]
            while self.at('op', ','):
                self.advance()
                syms.append(self.expect('name', what='a stock code').value.upper())
            self.expect('op', ']')
            return UniverseStmt(syms, **p)

        if self.at('kw', 'param'):
            self.advance()
            name = self.expect('name', what='a parameter name').value
            self.expect('op', '=', what="'=' and a list, like param n = [10, 20, 50]")
            return ParamStmt(name, self.expr(), **p)

        if self.at('kw', 'fn'):
            self.advance()
            name = self.expect('name', what='a function name').value
            self.expect('op', '(')
            params = []
            if not self.at('op', ')'):
                params.append(self.expect('name', what='a parameter name').value)
                while self.at('op', ','):
                    self.advance()
                    params.append(self.expect('name', what='a parameter name').value)
            self.expect('op', ')')
            if self.at('op', '='):
                self.advance()
                expr = self.expr()
                body = [Return(expr, line=expr.line, col=expr.col)]
            else:
                body = self.block()
            return FnDef(name, params, body, **p)

        if self.at('kw', 'if'):
            return self.if_statement()

        if self.at('kw', 'return'):
            self.advance()
            return Return(self.expr(), **p)

        if self.at('name') and self.peek().kind == 'op' and self.peek().value == '=':
            name = self.advance().value
            self.advance()
            return Assign(name, self.expr(), **p)

        return ExprStmt(self.expr(), **p)

    def if_statement(self):
        p = self.pos_of(self.expect('kw', 'if'))
        cond = self.expr()
        then = self.block()
        otherwise = []
        # allow `}` newline `else {`
        save = self.pos
        self.skip_newlines()
        if self.at('kw', 'else'):
            self.advance()
            otherwise = [self.if_statement()] if self.at('kw', 'if') else self.block()
        else:
            self.pos = save
        return If(cond, then, otherwise, **p)

    # expressions
    def expr(self):
        return self.or_expr()

    def or_expr(self):
        left = self.and_expr()
        while self.at('kw', 'or'):
            t = self.advance()
            left = BinOp('or', left, self.and_expr(), **self.pos_of(t))
        return left

    def and_expr(self):
        left = self.not_expr()
        while self.at('kw', 'and'):
            t = self.advance()
            left = BinOp('and', left, self.not_expr(), **self.pos_of(t))
        return left

    def not_expr(self):
        if self.at('kw', 'not'):
            t = self.advance()
            return UnaryOp('not', self.not_expr(), **self.pos_of(t))
        return self.compare()

    def compare(self):
        left = self.sum()
        if self.tok.kind == 'op' and self.tok.value in ('<', '>', '<=', '>=', '==', '!='):
            t = self.advance()
            left = BinOp(t.value, left, self.sum(), **self.pos_of(t))
        return left

    def sum(self):
        left = self.product()
        while self.tok.kind == 'op' and self.tok.value in ('+', '-'):
            t = self.advance()
            left = BinOp(t.value, left, self.product(), **self.pos_of(t))
        return left

    def product(self):
        left = self.unary()
        while self.tok.kind == 'op' and self.tok.value in ('*', '/'):
            t = self.advance()
            left = BinOp(t.value, left, self.unary(), **self.pos_of(t))
        return left

    def unary(self):
        if self.at('op', '-'):
            t = self.advance()
            return UnaryOp('-', self.unary(), **self.pos_of(t))
        return self.postfix()

    def postfix(self):
        node = self.atom()
        while True:
            if self.at('op', '('):
                if not isinstance(node, Name):
                    raise StockLangError("only named functions can be called", node.line, node.col)
                self.advance()
                args, kwargs = self.call_args()
                self.expect('op', ')')
                node = Call(node.name, args, kwargs, line=node.line, col=node.col)
            elif self.at('op', '['):
                t = self.advance()
                bars = self.expr()
                self.expect('op', ']')
                node = Lag(node, bars, **self.pos_of(t))
            else:
                return node

    def call_args(self):
        args, kwargs = [], {}
        while not self.at('op', ')'):
            if self.at('name') and self.peek().kind == 'op' and self.peek().value == '=':
                key = self.advance()
                self.advance()
                if key.value in kwargs:
                    raise StockLangError(f"argument '{key.value}' given twice", key.line, key.col)
                kwargs[key.value] = self.expr()
            else:
                if kwargs:
                    t = self.tok
                    raise StockLangError("positional argument after named argument", t.line, t.col)
                args.append(self.expr())
            if not self.at('op', ','):
                break
            self.advance()
        return args, kwargs

    def atom(self):
        t = self.tok
        p = self.pos_of(t)
        if t.kind == 'num':
            self.advance()
            return Num(t.value, **p)
        if t.kind == 'str':
            self.advance()
            return Str(t.value, **p)
        if t.kind == 'kw' and t.value in ('true', 'false'):
            self.advance()
            return Bool(t.value == 'true', **p)
        if t.kind == 'name':
            self.advance()
            return Name(t.value, **p)
        if self.at('op', '('):
            self.advance()
            e = self.expr()
            self.expect('op', ')')
            return e
        if self.at('op', '['):
            self.advance()
            items = [self.expr()]
            while self.at('op', ','):
                self.advance()
                items.append(self.expr())
            self.expect('op', ']')
            return ListLit(items, **p)
        got ='end of line' if t.kind == 'nl' else 'end of file' if t.kind == 'eof' else repr(t.value)
        raise StockLangError(f"expected a value, got {got}", t.line, t.col)


def parse(src):
    return Parser(tokenize(src)).parse_program()
