"""Presentation layer: figures and generated reports.

Kept separate from the analysis modules so that a change to how results are
displayed can never change what they say.
"""

from abtest.reporting import plots
from abtest.reporting.report import build_html_report, build_markdown_report

__all__ = ["plots", "build_html_report", "build_markdown_report"]
