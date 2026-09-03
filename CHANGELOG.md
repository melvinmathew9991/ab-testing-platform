# Changelog

All notable changes to this project are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added
- `abtest.exceptions`: `ABTestError` with `ConfigurationError`,
  `DataValidationError`, `InsufficientDataError` and `UnsupportedMetricError`,
  each also subclassing the built-in it replaces.
- `abtest.log`: library `NullHandler`, application-level configuration from
  `LOG_LEVEL` and `LOG_FORMAT`, JSON formatting and a duration context manager.
- `assignment_integrity` trust check for units exposed to both variants.
- Null-calibration test suite: A/A false-positive rates for the proportion and
  Welch tests, p-value uniformity, Benjamini-Hochberg family error rate, and
  end-to-end pipeline calibration.
- Project scaffolding: `requirements.txt`, `requirements-dev.txt`, `Makefile`,
  `.env.example`, `.dockerignore`, ruff configuration, GitHub Actions CI on
  Python 3.10-3.12, `docs/architecture.md`, `CONTRIBUTING.md`, `data/README.md`.

### Fixed
- Double-assignment detection ran after de-duplication and could never fire.
- CUPED failed on any metric containing missing values.
- The lift chart raised on a metric with a zero baseline.
- Duplicate metric names, identical variant labels and a unit column reused as
  the variant column were accepted silently.
- Segmenting by an unknown column raised a bare `KeyError`.
- A `TypeError` raised inside a resampling statistic was misread as a missing
  `axis` argument and silently downgraded the run to the slow path.

### Changed
- Package moved to a `src/` layout; presentation code grouped under
  `abtest.reporting`; `stats.multiple` and `stats.variance` renamed to
  `stats.multiple_testing` and `stats.variance_reduction`; `experiments/`
  renamed to `configs/`.
- Per-variant frames cached once at validation instead of re-scanning the
  frame on every access; power curves evaluated in a single vectorised pass.
- Test suite split into `unit/` and `integration/` with shared fixtures.
