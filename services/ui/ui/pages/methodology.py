"""What the tool does, and what it refuses to do.

A tool that gives statistical answers has to be legible about its choices,
because someone will eventually have to defend a decision made with it.
"""

from __future__ import annotations

import streamlit as st

from ui import components
from ui.config import get_settings


def render() -> None:
    st.title("Methodology")

    st.subheader("The decisions this tool makes for you")
    st.markdown(
        """
**Welch's t-test, never Student's.** A treatment can change a metric's variance
as well as its mean, and the degrees-of-freedom correction matters whenever the
arms differ in size.

**Two-sided, always.** A one-sided test cannot see a regression, and a
regression is the thing most worth seeing.

**Trust checks gate the result.** Sample-ratio mismatch and double assignment
are checked before anything is reported. A failed critical check blocks the
result rather than appearing as a footnote: if assignment is broken, the two
groups are not comparable and no statistical treatment repairs that.

**Multiple testing is corrected by default.** Three metrics at a 5% threshold
give roughly a 14% chance of at least one false positive. Metrics are only
called moved after adjustment; Benjamini-Hochberg is the default, Bonferroni is
available when a launch hangs on it.

**Guardrails respect direction.** A metric moving the wrong way is reported as a
regression, whatever the sign of the difference.

**Heavy tails are capped, not dropped.** Winsorizing at a shared percentile
keeps every randomised unit in its assigned arm; deleting outliers removes units
from one side and breaks the randomisation.

**Everything is seeded.** The same data and definition give the same numbers,
including the resampled ones.
        """
    )

    st.subheader("What it will not do")
    st.markdown(
        """
- **More than two variants.** Multi-arm tests need a shared-control correction
  that is not implemented here.
- **Ratio metrics with a varying denominator** - revenue per session, click-through
  where sessions differ per user. These need the delta method for their variance;
  treating them as per-unit values understates it.
- **Clustered units.** If several rows belong to one user, treating them as
  independent manufactures significance. One row per randomisation unit.
- **Segment on anything measured after assignment.** The interface only offers
  columns for segmentation; it is on you to ensure they were known before the
  experiment started. Splitting on something the treatment changed compares
  groups the treatment helped define.
        """
    )

    st.subheader("How a result is reached")
    st.markdown(
        """
1. **Data contract** - one row per unit, both variants present, binary metrics
   really binary. Duplicated units are reported and de-duplicated; units found in
   both arms are counted before that happens.
2. **Trust checks** - sample-ratio mismatch (chi-square at 0.001, strict because
   it runs on every experiment), assignment integrity, sparsity for binary
   metrics, outlier influence for continuous ones.
3. **Tests** - a two-proportion z-test for binary metrics, Welch's t-test for
   continuous ones, optionally with bootstrap intervals and permutation p-values.
4. **Correction** across the metric family.
5. **Decision** - a primary metric moving the intended way is a win; a primary or
   guardrail moving the wrong way blocks the launch; nothing moving is reported
   alongside what the experiment could have detected.
        """
    )

    st.subheader("Sources")
    st.markdown(
        """
The bundled example is the Cookie Cats mobile game A/B test (90,189 players,
published by Tactile Entertainment), widely used for teaching. The statistical
core is verified against `scipy` and closed-form results, and the assembled
pipeline is checked by running thousands of A/A experiments and confirming that
significance appears at exactly the advertised rate.
        """
    )

    settings = get_settings()
    st.divider()
    st.caption(f"Interface talking to `{settings.api_url}`")
    try:
        health = components.get_client().health()
        st.caption(
            f"API version {health['version']} ({health['environment']}) - "
            f"the full endpoint reference is at {settings.api_url}/docs"
        )
    except Exception:
        # The methodology text is worth reading even when the API is down.
        st.caption("API version unavailable - the service is not reachable right now.")
