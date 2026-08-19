class RuleError(Exception):
    """Base exception shown as a concise CLI diagnostic."""


class ValidationError(RuleError):
    """Raised when source, catalog, or DSL validation fails."""


class ExecutionError(RuleError):
    """Raised when a validated rule cannot be executed."""

