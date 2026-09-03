# Data

## `raw/cookie_cats.csv` (not committed)

The Cookie Cats mobile-game A/B test: 90,189 players randomised between a
first progression gate at level 30 (`gate_30`) and at level 40 (`gate_40`),
published by Tactile Entertainment and widely used for teaching.

One row per player:

| Column | Meaning |
|---|---|
| `userid` | Player identifier, the randomisation unit |
| `version` | Variant: `gate_30` (control) or `gate_40` (treatment) |
| `sum_gamerounds` | Rounds played in the first week after install |
| `retention_1` | Whether the player returned one day after install |
| `retention_7` | Whether the player returned seven days after install |

Fetched on demand rather than committed, so the repository carries code and
results but not a copy of someone else's dataset:

```bash
python analysis/fetch_data.py
```

The download is verified for the expected columns and row count.

## `processed/`

Reserved for derived tables. Empty today: the analysis reads the raw file and
computes everything in memory, so there is nothing worth persisting between
runs.
