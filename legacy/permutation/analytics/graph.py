import os, sys, logging
from warnings import warn
import pandas as pd
from numpy import arange
from dataclasses import dataclass
import matplotlib.ticker as tkr
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

sys.path.append("..")
sys.path.append("permutation")
from utils.db import LocalDB
from utils.params import (
    IMAGE_FOLDER,
    PERMUTATIONS_PICKLE_FILE,
    ABTestSettings,
)
from analytics.statistical_test import (
    ABTestStats,
    UserFlowStep,
    PowerAnalysis,
)
from utils.helper import get_index


@dataclass
class PowerGraph(ABTestSettings):
    """A class to draw graphs for power analysis."""

    folder: os.path = IMAGE_FOLDER
    power_analysis: PowerAnalysis = None
    permutation_tests: pd.DataFrame = None
    # Specific to drawing one graph
    page: UserFlowStep = UserFlowStep.CONFIRMATION
    metric: ABTestStats = ABTestStats.DIFFERENCE
    breakdown_col: tuple = None

    def __post_init__(self):
        """
        Load all the parameters from the power analysis after
        initiation
        """

        if self.power_analysis is None:
            self.import_local_and_check()
            self.power_analysis = PowerAnalysis.filtered_init(self.__dict__)

    def load_power_analysis(self):
        if self.power_analysis is None:            
            warn("No power analysis is available.")
        self.power_analysis.load_or_run()            
        # Inject all the parameters from the power analysis
        for k, v in self.power_analysis.__dict__.items():
            setattr(self, k, v)
        self.check_consistency()

        # Filter the data for a single step: “page”
        _data_ = (
            self.power_analysis.permutation_tests.filter(
                like=self.page.value, axis=0
            )
        )

        # Filter data source for the appropriate breakdown
        if self.breakdown:
            
            if self.breakdown_col:
                brk, col = self.breakdown_col
                _data_ = _data_.xs(col, level=brk)
            else:
                _data_ = _data_.xs(
                    ("All",) * len(self.breakdown),
                    level=tuple(self.breakdown),
                )

            # Check that data size match the permutation number
            assert (
                _data_.shape[0] == self.n_permutations
            ), "Wrong number of permutations"
        self.permutation_tests = _data_

    @property
    def data(self):
        return self.permutation_tests[self.metric.value]

    @property
    def min_max(self):
        return self.data.agg([min, max])

    @property
    def mde(self):
        return self.permutation_tests[
            ABTestStats.MDE.value
        ].mean()

    def _quant(self, quantile: float) -> float:
        """Return the value of the quantile"""
        quant_pos = int(self.data.shape[0] * (1 - quantile))
        return self.data.sort_values()[quant_pos]

    @property
    def edge(self) -> float:
        """
        Return the value of the edge of the confidence interval
        """
        return self._quant(self.alpha / 2)

    @property
    def quantile(self) -> float:
        """Return the value of power of the test"""
        return self._quant(self.beta)

    # Drawing graphs

    @staticmethod
    def __fix_hist_step_vertical_line_at_end(ax):
        """Helper method to remove the vertical line
        at the end of the histogram step plot"""
        axpolygons = [
            poly
            for poly in ax.get_children()
            if isinstance(poly, mpatches.Polygon)
        ]
        for poly in axpolygons:
            poly.set_xy(poly.get_xy()[:-1])

    def set_number_of_permutations(self, n: int = None):
        if n is None:
            n = self.data.shape[0]
        elif n > self.data.shape[0]:
            warn(
                f"Number of permutations asked {n} is greater "
                f"than the number of permutations available "
                f"{self.data.shape[0]}."
            )
            n = self.data.shape[0]
        return n

    def check_and_load_power_analysis(self, **kwargs):
        """Load the power analysis from the pickle file"""
        if not self.power_analysis:
            self.update_self_with_param(kwargs)
            self.power_analysis = PowerAnalysis(**kwargs)
            self.power_analysis.load_or_run()

    def draw_some_permutation_graph(
        self,
        n: int = None,
        breakdown_col: tuple = None,
        cumulative: bool = False,
    ):
        """
        Draw a histogram of the permutation test results
        for the first n permutations or all of them.
        Can be cumulative or not, default is not cumulative.
        """
        n = self.set_number_of_permutations(n)
        self.check_and_load_power_analysis()

        plt.cla()
        min_x, max_x = self.min_max
        data = self.data[:n]

        if not cumulative:
            ax = data.hist(bins=40)
            s = "s" if n > 1 else ""
            if self.metric == ABTestStats.DIFFERENCE:
                title = f"Difference between {n:,} pair{s} "
                title += "of presumably similar variants"
            else:
                warn(f"Titles for metric {self.metric.value} "+\
                    f"ane not defined.")
            if breakdown_col:
                title += "\nfor " + " in ".join(breakdown_col)
            ax.set_title(title)
            # $ pip install num2words / import num2words
            #   to spell out numbers if necessary

            ax.set_ylabel(
                f"Frequency among {n:,} permutations"
            )
            if n < 100:
                ax.set_ylim(0, 5)
            ax.yaxis.set_major_formatter(
                tkr.FuncFormatter(
                    lambda x, p: format(int(x), ",")
                )
            )

        else:
            ax = data.plot.hist(
                bins=arange(
                    min_x, max_x, (max_x - min_x) / 120
                ),
                cumulative=True,
                density=True,
                histtype="step",
            )
            title = (
                "Cumulative distribution of difference\n"
                + "between presumably similar variants"
            )
            if breakdown_col:
                title += "\n" + " ".join(breakdown_col)
            ax.set_title(title)
            ax.set_ylabel(
                f"Cumulative frequency among {n:,} permutations"
            )
            ax.yaxis.set_major_formatter(
                tkr.PercentFormatter(1)
            )
            self.__fix_hist_step_vertical_line_at_end(ax)

        ax.set_xlim(min_x, max_x)
        if self.metric == ABTestStats.DIFFERENCE:
            ax.set_xlabel("Difference between split variants")
        else:
            warn(
                f"Titles for metric {self.metric.value} are "
                f"not defined."
            )
        ax.xaxis.set_major_formatter(
            tkr.PercentFormatter(1.0, decimals=1)
        )

        # Naming the file
        cumul = "cumul_" if cumulative else ""
        brk_col = (
            "_".join(breakdown_col) if breakdown_col else ""
        )
        file_name = (
            cumul + brk_col + f"{n:_}_permutation_graph.png"
        )
        ax.figure.savefig(
            os.path.join(self.folder, file_name)
        )
        return ax

    def draw_liminal_aa_cases(self):
        """
        Draw a cumilative histogram of the permutation test
        results and mark the edges of the liminal area at the
        alpha level.
        """
        plot = self.draw_some_permutation_graph(
            cumulative=True
        )
        min_x, _ = self.min_max
        x = self.edge
        # Upper edge
        plot.hlines(1 - self.alpha / 2, min_x, x).set_color(
            "red"
        )
        plot.vlines(x, 0, 1 - self.alpha / 2).set_color("red")
        # Lower edge
        plot.hlines(self.alpha / 2, min_x, -x).set_color(
            "green"
        )
        plot.vlines(-x, 0, self.alpha / 2).set_color("green")
        title = (
            f"Cumulative distribution of difference\n"
            + f"with both tails at the {self.alpha*100:.0f}% "
            + f"significance level"
        )
        file_name = "liminal_aa_cases.png"
        if self.breakdown_col:
            title += " ".join(self.breakdown_col)
            file_name = (
                "_".join(self.breakdown_col) + file_name
            )
        plot.set_title(title)
        plot.figure.savefig(
            os.path.join(self.folder, file_name)
        )
        return plot

    def _power_curve(self, **kwargs):
        """
        How likely is it to detect a significant difference
        given a certain effect of the alternative treatment?
        """
        plt.cla()
        breakdown_col = kwargs.get("breakdown_col")
        if breakdown_col:
            brk, col = breakdown_col
            self.permutation_tests = (
                self.power_analysis.permutation_tests.xs(
                    col, level=brk
                )
            )
        mde = self.mde
        min_x, max_x = self.min_max
        # self.data - mde for negative detection
        plot = (self.data + mde).plot.hist(
            bins=arange(
                min_x + mde,
                max_x + mde,
                (max_x - min_x) / 120,
            ),
            cumulative=True,
            density=True,
            histtype="step",
            color="brown",
        )
        self.__fix_hist_step_vertical_line_at_end(plot)
        plot.set_xlim(0, max_x + mde)
        plot.set_ylabel(
            "Likelihood of detecting a significant difference"
        )
        plot.set_xlabel("Impact of the alternative treatment")
        plot.xaxis.set_major_formatter(
            tkr.PercentFormatter(1.0, decimals=1)
        )
        plot.yaxis.set_major_formatter(
            tkr.PercentFormatter(1)
        )
        return plot, mde

    def draw_power_curve(self, **kwargs):
        """
        Draw a power curve:
        """

        plot, _ = self._power_curve(**kwargs)
        title = "Power curve"
        file_name = "power_curve.png"

        breakdown_col = kwargs.get("breakdown_col")
        if breakdown_col:
            title += "\n" + " ".join(breakdown_col)
            file_name = (
                "_".join(breakdown_col) + "_" + file_name
            )
        plot.set_title(title)
        plot.figure.savefig(
            os.path.join(self.folder, file_name)
        )
        return plot

    def draw_reliably_detected(self, **kwargs):
        """
        Draw a power curve and mark the reliably
        detected effect at the beta level.
        """
        breakdown_col = kwargs.get("breakdown_col")
        plot, mde = self._power_curve(**kwargs)

        # Vertical intercept line
        x = self.quantile
        plot.vlines(x + mde, 0, 1 - self.beta).set_color(
            "teal"
        )
        # Horizontal line at 80%
        plot.hlines(1 - self.beta, 0, x + mde).set_color(
            "teal"
        )

        # TODO: Merge all title and file saving operation
        #       into a base class graph Object or decorator
        title = "Power curve with reliably detected effect"
        if breakdown_col:
            title += "\n" + " ".join(breakdown_col)
        plot.set_title(title)

        file_name = "reliably_detected_effect.png"
        if breakdown_col:
            file_name = (
                "_".join(breakdown_col) + "_" + file_name
            )
        plot.figure.savefig(
            os.path.join(self.folder, file_name)
        )
        return plot

    def draw_p_value_distribution(self):
        """Draw a histogram of the p-values.
        Expected to be uniform on [0, 1]."""
        plt.cla()
        data = self.permutation_tests[
            ABTestStats.P_VALUE.value
        ]
        plot = data.plot.hist(bins=40, color="purple")
        plot.set_title(
            f"p-values for {self.n_permutations:,} permutations"
        )
        plot.set_xlabel("p-value")
        plot.set_ylabel("Frequency")
        plot.figure.savefig(
            os.path.join(self.folder, "p_values.png")
        )
        # TODO: Statistical test p-values uniform distribution
        return plot

    def draw_all_permutation_graphs(self) -> None:
        """
        Draw all permutation graphs.
        This is the main entry point for this class.
        The graphs are saved in the /docs/ folder to
        support the explanations in the .md documentation.
        """
        for i in range(4):
            n = 10**i
            self.draw_some_permutation_graph(n)
        self.draw_some_permutation_graph()
        self.draw_some_permutation_graph(cumulative=True)
        self.draw_liminal_aa_cases()
        self.draw_p_value_distribution()
        self.draw_power_curve()
        self.draw_reliably_detected()

    def draw_categorical_power_graph(
        self, breakdown_col: tuple = None
    ) -> None:
        if breakdown_col is None:
            _bkd_ = self.values[0]
            _col_ = self.values[_bkd_][0]
            breakdown_col = (_bkd_, _col_)
            warn(
                f"Breakdown column not specified."
                f"Using {_bkd_} and {_col_}."
            )
        brk, col = breakdown_col

        # Validity checks
        if self.power_analysis.values is not None:
            if self.values is None:
                self.values = self.power_analysis.values

            if brk not in self.values.keys():
                raise ValueError(
                    f"Breakdown {brk} not in "
                    f"{self.values.keys()}"
                )
            if col not in self.values[brk]:
                raise ValueError(
                    f"Column {col} not a possible value for "
                    f"{brk}; options are: {self.values[brk]}"
                )

        self.permutation_tests = (
            self.power_analysis.permutation_tests.xs(
                col, level=brk
            )
        )
        self.draw_reliably_detected(
            breakdown_col=breakdown_col
        )

    def draw_all_categorical_power_graphs(
        self, breakdown: tuple = None
    ) -> None:
        if not self.values:
            if self.power_analysis.permutation_tests is None:
                warn("Missing permutation tests data.")
            self.values = get_index(
                self.power_analysis.permutation_tests.index
            )

        if breakdown is None:
            if self.breakdown:
                breakdown = self.breakdown
            else:
                # This draws all possible categorical graphs
                breakdown = self.values.keys()
        for bkd in breakdown:
            for col in self.values[bkd]:
                self.draw_categorical_power_graph((bkd, col))


if __name__ == "__main__":
    # Load pickled power analysis data and draw graphs
    db = LocalDB()
    power_analysis = PowerAnalysis(db.conn)
    power_analysis.permutation_tests = pd.read_pickle(
        PERMUTATIONS_PICKLE_FILE
    )
    power_analysis.should_run = False
    power_graph = PowerGraph(db.conn, power_analysis)
    power_graph.load_power_analysis()
    power_graph.draw_all_permutation_graphs()
