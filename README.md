# A/B Testing: a toolkit and a worked experiment

A small, opinionated Python toolkit for analysing controlled experiments, plus a
complete analysis of a real one - the [Cookie Cats](https://www.kaggle.com/datasets/yufengsui/mobile-games-ab-testing)
mobile-game gate placement test, 90,189 players.

The toolkit encodes the parts of experiment analysis that are easy to get wrong:
Welch's t-test with the right degrees of freedom, sample-ratio checks before any
result is read, multiple-testing correction across the metric family, honest
power analysis, and alpha spending for mid-flight peeking. The analysis shows
what those tools say about a real decision.

```bash
pip install -e .
python analysis/fetch_data.py           # 1.5 MB public dataset
python analysis/run_cookie_cats.py      # analysis + report + figures
```

Output: [`reports/cookie_cats_report.html`](reports/cookie_cats_report.html) -
a standalone report with figures embedded.

---

## The finding

**Recommendation: do not ship gate 40.**

Moving the first progression gate from level 30 to level 40 was supposed to let
players go deeper before being blocked, and so improve retention. It did the
opposite where it counts.

| Metric | Role | Gate 30 | Gate 40 | Lift | 95% CI | p (BH-adj.) | Verdict |
|---|---|---:|---:|---:|---:|---:|---|
| Day-1 retention | primary | 44.82% | 44.23% | −1.32% | −2.77% to +0.13% | 0.112 | no effect |
| Day-7 retention | primary | 19.02% | 18.20% | **−4.31%** | −6.98% to −1.64% | **0.0047** | **regression** |
| Game rounds (99th pct. cap) | guardrail | 49.14 | 48.85 | −0.57% | −2.81% to +1.66% | 0.615 | no effect |

Day-7 retention falls by 0.82 percentage points. The confidence interval sits
entirely below zero, the Bayesian posterior puts the probability that gate 40 is
better at **0.1%**, and a 10,000-draw permutation test on the engagement metric
agrees with the parametric one (p = 0.607 vs 0.615). Every route to the answer
gives the same answer.

![Relative lift by metric](reports/figures/lift_forest.png)

### Three things the analysis turns up that a naive read would miss

**1. The engagement metric is one player wide.** Raw mean rounds played differ by
−2.21% between arms. Remove the single most extreme player - one account with
49,854 rounds, against a median of 16 - and the difference collapses to −0.08%.
That is why the guardrail is winsorized at the 99th percentile (a shared cap
computed on pooled data, applied to both arms) before it is tested. Capping keeps
every randomised unit in its arm; dropping outliers would not.

![Game rounds distribution](reports/figures/gamerounds_distribution.png)

**2. Ninety thousand users is not "enough data" in the abstract.** At this
sample size the experiment could reliably detect a 3.9% relative change in day-7
retention at 80% power. The observed −4.3% only just clears that bar. Detecting
a 2% change - a perfectly plausible size for a gate tweak - would have needed
about **337,000 players, 3.7× this experiment**. The day-1 result is not
evidence of no effect; it is an experiment that could not have seen a small one.

![Power curve](reports/figures/power_curve.png)

**3. Checking daily would have "found" the answer far too early.** Replaying the
experiment in a random arrival order and testing at eight points, a fixed
p < 0.05 threshold fires at all 8 looks - including at 12% of traffic, where the
O'Brien-Fleming boundary still demands z > 5.5. The direction happened to be
right here; the method that produced it is not one that can be trusted to be.

![Sequential analysis](reports/figures/sequential.png)

### Calls the analysis makes explicitly

- **The split is uneven, but not broken.** 44,700 / 45,489 is a 49.56/50.44
  split - chi-square p = 0.0086. That would fail a naive 0.05 threshold. The SRM
  check uses 0.001 deliberately: it runs on every experiment, and at that
  threshold this imbalance is within what randomisation produces. It is
  reported, not buried.
- **No segment breakdown.** The dataset has no pre-assignment attributes. The
  only other column, rounds played, is measured after assignment and is affected
  by the treatment - splitting on it would compare groups the treatment helped
  define. The toolkit supports segmentation with correction across slices; this
  experiment has nothing legitimate to segment on.
- **Two primary metrics, so p-values are corrected.** Benjamini-Hochberg across
  the family of three. Day-7 survives correction; nothing else was close.

---

## The toolkit

```python
from abtest import ExperimentConfig, ExperimentData, Experiment

config  = ExperimentConfig.from_yaml("configs/cookie_cats.yml")
data    = ExperimentData.from_file("data/raw/cookie_cats.csv", config)
results = Experiment(data, config).run(resample=True)

results.summary()        # one row per metric
results.checks_frame()   # SRM, sparsity, outlier influence, data quality
results.decision()       # ship / do not ship, with the reasoning
```

Command line:

```bash
abtest analyze --config configs/cookie_cats.yml --data data/raw/cookie_cats.csv \
               --html reports/out.html --segment-by country device
abtest checks  --config ... --data ...          # trust checks only, exit 1 on failure
abtest power   --baseline 0.19 --mde 0.02       # traffic needed before you start
```

### What is in it

| Module | Contents |
|---|---|
| `src/abtest/config.py` | Declarative experiment definition (YAML or code): metrics, roles, direction, alpha, power, correction method |
| `src/abtest/data.py` | Unit-level data contract: required columns, one row per unit, binary metrics really binary; fatal problems raise, the rest are reported |
| `src/abtest/checks.py` | Sample-ratio mismatch, normal-approximation sparsity, outlier influence, segment balance |
| `src/abtest/stats/frequentist.py` | Two-proportion z-test, Welch's t-test, CIs, observed power, MDE |
| `src/abtest/stats/power.py` | Sample size, MDE for a given sample, power curves, for proportions and means |
| `src/abtest/stats/bootstrap.py` | Percentile bootstrap CIs and permutation tests, batched and vectorised |
| `src/abtest/stats/bayesian.py` | Beta-Binomial posterior: P(B > A), expected loss, credible interval on lift |
| `src/abtest/stats/sequential.py` | O'Brien-Fleming boundaries and alpha spending for interim looks |
| `src/abtest/stats/variance_reduction.py` | CUPED variance reduction, winsorization with a shared cap |
| `src/abtest/stats/multiple_testing.py` | Bonferroni and Benjamini-Hochberg |
| `src/abtest/experiment.py` | Orchestration: validate → check → test → correct → decide |
| `src/abtest/reporting/` | Figures and a self-contained HTML/Markdown report |
| `src/abtest/exceptions.py`, `log.py` | Typed failures and structured logging, so callers can act on an error and an operator can see what ran |

### Design decisions worth knowing

- **Welch by default, never Student.** A treatment can change a metric's
  variance as well as its mean. The degrees-of-freedom calculation pairs each
  variance with the sample size it came from - a detail that silently corrupts
  p-values when the arms are unequal, and which the test suite pins directly.
- **Two-sided, always.** A one-sided test cannot see a regression, and a
  regression is the thing most worth seeing.
- **Trust checks gate the result, not decorate it.** A failed SRM makes
  `decision()` return "do not use this result" regardless of how good the
  p-values look. The CLI exits non-zero.
- **Correction is on by default.** Testing three metrics at α = 0.05 gives about
  a 14% chance of at least one false positive. Metrics are only called moved
  after adjustment.
- **Verdicts respect metric direction.** A guardrail moving the wrong way is a
  regression, not a win, whatever the sign of the difference.
- **Every result is seeded and reproducible.** Same config plus same data gives
  the same numbers, including the resampling ones.

---

## Testing

```bash
make test         # 153 tests, including calibration (~50s)
make test-fast    # skip the calibration runs
make lint         # ruff
```

The statistical core is verified against `scipy` and closed-form identities
rather than recorded output: Welch against `scipy.stats.ttest_ind(equal_var=False)`
to 1e-12, sample size against the textbook formula, power and MDE as inverses of
each other, O'Brien-Fleming boundaries against their known values (3.92 / 2.77 /
2.26 / 1.96 at four looks), bootstrap intervals against the parametric interval
on normal data, CUPED for unbiasedness plus variance reduction across 20
simulated experiments.

Above those sit **calibration tests**, which run thousands of A/A experiments
and assert that significance appears at exactly the advertised 5%: for the
proportion test, for Welch with deliberately unequal arms and variances, for the
uniformity of the null p-value distribution, for the Benjamini-Hochberg family
error rate, and for the assembled pipeline end to end. Unit tests confirm each
formula; these confirm the pipeline built from them, which is where a mis-wired
correction or a filter applied to one arm would otherwise hide. Every simulation
is seeded.

The pipeline tests also build synthetic experiments with a known effect and
assert the toolkit reaches the right decision - including that a broken split or
units assigned to both arms invalidate the result entirely.

## Project structure

```
src/abtest/          the toolkit
  stats/             frequentist, bootstrap, power, bayesian, sequential,
                     variance_reduction, multiple_testing
  reporting/         plots and generated reports
services/api/        FastAPI service (app/, Dockerfile, requirements.txt)
analysis/            fetch_data.py, run_cookie_cats.py (the showcase)
configs/             cookie_cats.yml - the experiment definition
tests/               unit/, integration/, api/ (153 tests) and shared fixtures
reports/             generated HTML/Markdown/JSON report and figures
docs/                architecture.md, plus the inherited articles in legacy/
legacy/              the original educational codebase, archived
```

## The API

The toolkit is also served as an HTTP API, which is what the Streamlit
frontend talks to.

```bash
make api                                   # http://localhost:8000/docs
# or the container, which is what gets deployed
docker build -f services/api/Dockerfile -t ab-api .
docker run --rm -p 8000:8080 ab-api
```

| Endpoint | Purpose |
|---|---|
| `GET /health`, `/ready` | Liveness, and whether demo data is available |
| `GET /api/v1/datasets` | Bundled demo datasets and their default experiment definitions |
| `POST /api/v1/data/inspect` | Profile an upload: columns, types, candidate unit/variant columns |
| `POST /api/v1/experiments/validate` | Data contract and trust checks only |
| `POST /api/v1/experiments/analyze` | Full analysis: metrics, checks, decision |
| `POST /api/v1/experiments/report` | The same analysis as a downloadable HTML report |
| `POST /api/v1/power/sample-size`, `/mde`, `/curve` | Planning before launch |
| `POST /api/v1/sequential/boundaries` | Interim looks against an alpha-spending boundary |

`/docs` serves the generated OpenAPI reference.

The analysis endpoints take one multipart request: a `payload` form field
holding the JSON experiment definition, plus an optional file. Without a file,
`dataset_id` selects a bundled dataset.

```bash
curl -X POST http://localhost:8000/api/v1/experiments/analyze   -F 'payload={"config": {"name": "gate test", "unit_col": "userid",
       "variant_col": "version", "control": "gate_30", "treatment": "gate_40",
       "metrics": [{"name": "retention_7", "column": "retention_7",
                    "type": "binary", "primary": true}]},
       "dataset_id": "cookie_cats"}'
```

Failures are typed rather than generic: an invalid experiment definition or
malformed data returns 422, data too thin to analyse returns 409, an upload
over the limit returns 413, and every response carries an `X-Request-ID` that
matches the server log. Limits (`MAX_UPLOAD_MB`, `MAX_ROWS`,
`MAX_PERMUTATIONS`) come from the environment - see `.env.example`.

Note that a failed critical check is not an error: the analysis returns 200
with the checks and a recommendation not to use the result.

## Development

```bash
pip install -e ".[dev]"
python analysis/fetch_data.py
make test-fast
```

`make` targets cover install, test, lint, format, analysis and clean.
Configuration is read from the environment (`LOG_LEVEL`, `LOG_FORMAT`); see
`.env.example`. CI runs lint and the full suite on Python 3.10, 3.11 and 3.12.

### Known limits

- Two variants per experiment; multi-arm tests are not supported.
- `Experiment.sensitivity()` is closed-form for binary metrics only. For
  continuous metrics use `abtest.stats.power.sample_size_means`.
- Metrics are per-unit values. Ratio metrics with a varying denominator need
  the delta method, which is not implemented yet.

## Data

Cookie Cats A/B test, 90,189 players, published by Tactile Entertainment and
widely used for teaching. `analysis/fetch_data.py` downloads it; it is not
committed. One row per player: variant (`gate_30` / `gate_40`), rounds played in
the first week, and day-1 / day-7 retention flags.

## Notes on this repository

`docs/architecture.md` describes the target design for the deployed
application. `docs/legacy/` holds background articles from the original
educational project this repository grew out of, and `legacy/` that original
codebase, archived unchanged; neither is imported by the toolkit.
