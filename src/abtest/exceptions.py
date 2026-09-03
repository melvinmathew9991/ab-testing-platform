"""Exception hierarchy.

The distinction that matters is *whose fault it is*, because that is what a
caller has to act on: a misconfigured experiment and a dataset too thin to
analyse need different responses, and neither is a bug. The HTTP layer maps
these types directly onto status codes, so the split is drawn where the
service needs it rather than where the code happens to fail.

Every type also subclasses the built-in it replaces, so existing callers
catching ``ValueError`` keep working.
"""
from __future__ import annotations


class ABTestError(Exception):
    """Base class for every error this package raises deliberately.

    Anything that escapes as a different type is a bug, not a handled
    condition - which is exactly the line an API layer needs to draw between
    a 4xx and a 5xx.
    """


class ConfigurationError(ABTestError, ValueError):
    """The experiment definition is invalid or self-contradictory.

    Raised before any data is touched: unknown metric type, alpha outside
    (0, 1), a split that does not sum to one, duplicate metric names.
    """


class DataValidationError(ABTestError, ValueError):
    """The data does not satisfy the contract the analysis depends on.

    Missing columns, a variant that is absent, non-binary values in a binary
    metric, a covariate that does not align with its metric.
    """


class InsufficientDataError(ABTestError, ValueError):
    """The data is well formed but too thin to compute the requested result.

    An empty arm, fewer than two observations for a t-test, a sequential
    analysis with no looks. Distinct from ``DataValidationError`` because
    nothing is wrong with the input - there is simply not enough of it.
    """


class UnsupportedMetricError(ABTestError, ValueError):
    """The operation is not defined for this metric type.

    Raised where a capability genuinely does not exist yet, rather than
    where an input is wrong - for example closed-form sensitivity, which is
    implemented for binary metrics only.
    """
