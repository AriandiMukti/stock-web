class StockLangError(Exception):
    """Any error in a StockLang script, carrying where in the source it happened."""

    def __init__(self, message, line=None, col=None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.col = col

    def render(self, src=None, filename='<script>'):
        if self.line is None:
            return f"error: {self.message}"
        out = f"{filename}:{self.line}:{self.col}: error: {self.message}"
        if src is not None:
            lines = src.splitlines()
            if 0 < self.line <= len(lines):
                out += f"\n    {lines[self.line - 1]}\n    {' ' * (self.col - 1)}^"
        return out
