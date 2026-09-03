# Contributing

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python analysis/fetch_data.py
```

## Working

```bash
make test-fast     # suite without the calibration runs
make test          # everything, including calibration (~30s)
make lint          # ruff
make format        # ruff format
make analysis      # rebuild the Cookie Cats report and figures
```

## Expectations for a change

- **Tests come with it.** Statistical code is tested against a reference
  (scipy, a closed-form result, or a simulation), never against previously
  recorded output - a snapshot test locks in whatever bug was present when it
  was written.
- **Errors are typed.** Raise from `abtest.exceptions` so callers, including
  the HTTP layer, can act on the failure without reading the message.
- **Complexity is a design input.** Prefer one pass over repeated scans, and
  vectorise anything that will run inside a request.
- **Decisions trace to the use case.** A new option needs a user whose
  decision it changes.

## Branches and commits

One branch per unit of work, named for it. Commit messages describe the change
and why it was needed; they carry no tool or session metadata.
