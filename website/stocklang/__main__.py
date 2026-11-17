"""
Command line entry point.

    python -m stocklang FILE.stk        run a script
    python -m stocklang run FILE.stk    same thing
    python -m stocklang                 interactive prompt (REPL)
"""
import sys
import time

from .errors import StockLangError
from .interpreter import Interpreter, run_source
from .parser import parse
from . import report

BANNER = """StockLang interactive prompt. Type help() for functions, exit to quit.
Start with a stock, e.g.:  stock BBCA"""


def run_file(path):
    try:
        with open(path, encoding='utf-8') as f:
            src = f.read()
    except OSError as e:
        print(f"error: can't open {path}: {e.strerror}")
        return 1
    t0 = time.perf_counter()
    try:
        run_source(src, filename=path, script_path=path)
    except StockLangError as e:
        print(e.render(src, path))
        return 1
    print(f"(done in {time.perf_counter() - t0:.2f}s)")
    return 0


def repl():
    print(BANNER)
    interp = Interpreter()
    buffer = []
    while True:
        prompt = '... ' if buffer else (f"{interp.symbol}> " if interp.symbol else '> ')
        try:
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not buffer and line.strip() in ('exit', 'quit'):
            return 0
        buffer.append(line)
        src = '\n'.join(buffer)
        # Keep reading while brackets are open (multi-line fn / if / call).
        if any(src.count(a) > src.count(b) for a, b in ('{}', '()', '[]')):
            continue
        buffer = []
        if not src.strip():
            continue
        try:
            stmts = parse(src)
            result = interp.run(stmts)
            if result is not None:
                print(report.value(result))
        except StockLangError as e:
            print(e.render(src, '<input>'))


def main(argv):
    args = argv[1:]
    if args and args[0] == 'run':
        args = args[1:]
    if not args:
        return repl()
    if args[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    return run_file(args[0])


if __name__ == '__main__':
    sys.exit(main(sys.argv))
