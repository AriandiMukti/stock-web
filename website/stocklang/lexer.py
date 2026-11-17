"""
Lexer: turns StockLang source text into a flat list of tokens.

Number literals understand the shorthand people use when talking about
money and fees, so scripts read the way you'd say them out loud:
    10K -> 10_000      10M -> 10_000_000      1.5B -> 1_500_000_000
    0.15% -> 0.0015
"""
from dataclasses import dataclass

from .errors import StockLangError

KEYWORDS = {
    'and', 'or', 'not', 'true', 'false',
    'if', 'else', 'fn', 'return',
    'stock', 'universe', 'param',
}

SUFFIXES = {'K': 1e3, 'M': 1e6, 'B': 1e9, 'T': 1e12}

# Longest first so '>=' wins over '>'.
OPERATORS = ['==', '!=', '<=', '>=', '+', '-', '*', '/', '<', '>', '=',
             '(', ')', '[', ']', '{', '}', ',', ';']


@dataclass
class Token:
    kind: str      # 'num', 'str', 'name', 'kw', 'op', 'nl', 'eof'
    value: object
    line: int
    col: int

    def __repr__(self):
        return f"{self.kind}:{self.value!r}@{self.line}:{self.col}"


def tokenize(src):
    tokens = []
    i, line, col = 0, 1, 1
    n = len(src)
    open_brackets = []   # open ( and [ -- newlines inside them don't end a statement

    def add(kind, value, l, c):
        tokens.append(Token(kind, value, l, c))

    while i < n:
        ch = src[i]

        if ch == '\n':
            if not open_brackets:
                add('nl', '\n', line, col)
            i += 1
            line += 1
            col = 1
            continue
        if ch in ' \t\r':
            i += 1
            col += 1
            continue
        if ch == '#' or src.startswith('//', i):
            while i < n and src[i] != '\n':
                i += 1
            continue

        start_col = col

        if ch.isdigit() or (ch == '.' and i + 1 < n and src[i + 1].isdigit()):
            j = i
            while j < n and (src[j].isdigit() or src[j] in '._'):
                j += 1
            text = src[i:j].replace('_', '')
            try:
                value = float(text)
            except ValueError:
                raise StockLangError(f"invalid number '{src[i:j]}'", line, start_col)
            if j < n and src[j] in SUFFIXES and not (j + 1 < n and (src[j + 1].isalnum() or src[j + 1] == '_')):
                value *= SUFFIXES[src[j]]
                j += 1
            elif j < n and src[j] == '%':
                value /= 100
                j += 1
            add('num', value, line, start_col)
            col += j - i
            i = j
            continue

        if ch.isalpha() or ch == '_':
            j = i
            while j < n and (src[j].isalnum() or src[j] == '_'):
                j += 1
            word = src[i:j]
            add('kw' if word in KEYWORDS else 'name', word, line, start_col)
            col += j - i
            i = j
            continue

        if ch in '"\'':
            j = i + 1
            while j < n and src[j] != ch and src[j] != '\n':
                j += 1
            if j >= n or src[j] != ch:
                raise StockLangError("unterminated string", line, start_col)
            add('str', src[i + 1:j], line, start_col)
            col += j + 1 - i
            i = j + 1
            continue

        for op in OPERATORS:
            if src.startswith(op, i):
                if op in ('(', '['):
                    open_brackets.append((op, line, start_col))
                elif op in (')', ']') and open_brackets:
                    open_brackets.pop()
                add('op', op, line, start_col)
                i += len(op)
                col += len(op)
                break
        else:
            raise StockLangError(f"unexpected character '{ch}'", line, start_col)

    if open_brackets:
        op, l, c = open_brackets[-1]
        raise StockLangError(f"'{op}' is never closed", l, c)
    add('nl', '\n', line, col)
    add('eof', None, line, col)
    return tokens
