# Legacy code (archived)

The original educational codebase this repository grew out of: a DuckDB and
`fake-web-events` simulation that generated synthetic funnel events and ran
permutation-based power analysis on them.

It is kept for reference and is **not** imported, tested or maintained by the
current toolkit. It does not run as-is - `pyproject.toml` listed an invalid
dependency (`4 = "^8.8.8"`), several modules depend on pandas 1.x behaviour, and
`compute_t_test` paired each variance with the other arm's sample size when
computing Welch degrees of freedom, so its p-values drifted whenever the arms
were unequal.

The current `abtest` package replaces it. The background articles in `docs/` came
from the same project and are still worth reading.
