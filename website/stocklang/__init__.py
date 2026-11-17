"""
StockLang: a small language for IDX stock analysis.

    from stocklang import run_source
    run_source(open('examples/golden_cross.stk').read())

or from the command line (inside the website folder):

    python -m stocklang examples/golden_cross.stk
    python -m stocklang            # interactive prompt
"""
from .errors import StockLangError
from .interpreter import Interpreter, run_source
from .parser import parse

__all__ = ['StockLangError', 'Interpreter', 'run_source', 'parse']
