"""Multiple-testing corrections.

Testing five metrics at alpha = 0.05 gives roughly a 23% chance of at least
one false positive. Correcting is not optional once an experiment reports
more than one metric.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from abtest.exceptions import ConfigurationError, DataValidationError


def adjust_pvalues(
    p_values: Sequence[float],
    method: str = "bh",
    alpha: float = 0.05,
    labels: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Adjust a family of p-values.

    Args:
        method: ``bonferroni`` controls the family-wise error rate (strict,
            use for ship decisions); ``bh`` (Benjamini-Hochberg) controls the
            false discovery rate (better for exploratory metric sweeps);
            ``none`` passes the values through unchanged.

    Returns:
        DataFrame with the raw p-value, the adjusted p-value and the
        post-correction significance flag, in the input order.
    """
    p = np.asarray(list(p_values), dtype=float)
    if p.size == 0:
        return pd.DataFrame(columns=["label", "p_value", "p_adjusted", "significant", "method"])
    if np.any((p < 0) | (p > 1)):
        raise DataValidationError("p-values must lie in [0, 1]")
    method = method.lower()
    m = p.size

    if method == "none":
        adjusted = p.copy()
    elif method == "bonferroni":
        adjusted = np.minimum(p * m, 1.0)
    elif method in ("bh", "fdr", "fdr_bh"):
        order = np.argsort(p)
        ranked = p[order] * m / np.arange(1, m + 1)
        # Enforce monotonicity from the largest p-value downwards.
        ranked = np.minimum.accumulate(ranked[::-1])[::-1]
        adjusted = np.empty_like(ranked)
        adjusted[order] = np.minimum(ranked, 1.0)
    else:
        raise ConfigurationError(f"Unknown correction method {method!r}")

    return pd.DataFrame(
        {
            "label": list(labels) if labels is not None else list(range(m)),
            "p_value": p,
            "p_adjusted": adjusted,
            "significant": adjusted < alpha,
            "method": method,
        }
    )
