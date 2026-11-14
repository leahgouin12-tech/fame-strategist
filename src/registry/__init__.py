"""The repository audit and its registry.

Nothing is re-exported from here. `audit` is both this package's main module and a function
inside it, so binding the name at package level would hand `from src.registry import audit`
the function and break every caller that reaches for `audit.routes()`.
"""
