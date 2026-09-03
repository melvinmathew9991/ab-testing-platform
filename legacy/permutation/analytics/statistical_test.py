import os, sys, logging
from warnings import warn
from dataclasses import dataclass
import pandas as pd
import numpy as np
from tqdm import tqdm
from scipy.stats import t
from random import choices
from pandera import (
    DataFrameSchema,
    Column,
    check_input,
    check_output,
)
from pandera.dtypes import Int64, Int32

sys.path.append("..")
sys.path.append("permutation")
from utils.db import LocalDB, DBConnection
from utils.params import (
    UNIT_ID,
    STEP_NAME,
    VARIANT,
    NUMERATOR,
    DENOMINATOR,
    METRIC_NAME,
    UserFlowStep,
    STEPS_LABEL_URL,
    Assignment,
    ABTestStats,
    PowerAnalyticStats,
    ABTestSettings,
    AB_TEST_PICKLE_FILE,
    PERMUTATIONS_PICKLE_FILE,
    store_file,
    ALPHA,
    BETA,
    N_PERMUTATIONS,
)
from analytics.reporting import (
    Report,
    FlexibleReport,
    DetailedReport,
    user_progress_schema,
    pivoted_cr_schema,
    conversion_rate_raw_schema,
)
from utils.helper import get_index

# Dataframe structures for type hinting
ab_test_result_schema = DataFrameSchema(
    {
        ABTestStats.DIFFERENCE.value: Column(
            float, nullable=True
        ),
        ABTestStats.STDEV.value: Column(float, nullable=True),
        ABTestStats.T_SCORE.value: Column(
            float, nullable=True
        ),
        ABTestStats.DEGREES_OF_FREEDOM.value: Column(
            Int32, nullable=True
        ),
        ABTestStats.P_VALUE.value: Column(
            float, nullable=True
        ),
        ABTestStats.MDE.value: Column(float, nullable=True),
        ABTestStats.SIGNIFICANT.value: Column(
            bool, nullable=True
        ),
        # "difference": Column(float, nullable=True),
        # "stdev": Column(float, nullable=True),
        # "t-score": Column(float, nullable=True),
        # "degrees_of_freedom": Column(int, nullable=True),
        # "p-value": Column(float, nullable=True),
        # "minimum_detectable_effect": Column(float, nullable=True),
        # "significant": Column(bool, nullable=True),
        #
        # 'reliably_detectable_effect': Column(float, nullable=True),
        # Add categories
    },
)
permutation_test_detail_schema = ab_test_result_schema
describe_schema = DataFrameSchema(
    {
        "count": Column(int),
        "mean": Column(float),
        "std": Column(float),
        "min": Column(float),
        "25%": Column(float),
        "50%": Column(float),
        "75%": Column(float),
        "max": Column(float),
    }
)
permutation_test_result_schema = DataFrameSchema(
    {
        (ABTestStats.SIGNIFICANT.value, "mean"): Column(
            float
        ),
        (ABTestStats.DIFFERENCE.value, "std"): Column(float),
        **{
            (ABTestStats.P_VALUE.value, k): v
            for k, v in describe_schema.columns.items()
        },
    }
)
power_analysis_schema = DataFrameSchema(
    {
        PowerAnalyticStats.MEAN_MDE.value: Column(float),
        PowerAnalyticStats.QUANT_DIFF.value: Column(float),
        PowerAnalyticStats.REL_DET_EFFECT.value: Column(
            float
        ),
    }
)


# Helper statictical function
@check_input(pivoted_cr_schema)
@check_output(ab_test_result_schema)
def compute_t_test(
    c: pd.DataFrame,
    alpha: float = ALPHA,
    count_name: str = DENOMINATOR,
    event_name: str = NUMERATOR,
    metric_name: str = METRIC_NAME,
    variant: list = Assignment.list(),
) -> pd.DataFrame:  # ABTestResult:
    """
    Compute the t-test for the given conversion rate table,
    returns the same dataframe with the columns ABTestStats.
    """
    v0 = variant[0]
    v1 = variant[1]
    # We use the Welch's t-test as variances can be uneven.
    c[(ABTestStats.VARIANCE.value, v0)] = (
        c[metric_name][v1]
        * (1 - c[metric_name][v1])
        / c[count_name][v1]
    )  # .fillna(0).replace(np.inf, 0)
    c[(ABTestStats.VARIANCE.value, v1)] = (
        c[metric_name][v0]
        * (1 - c[metric_name][v0])
        / c[count_name][v0]
    )  # .replace(np.inf, 0)
    c[ABTestStats.STDEV.value] = (
        c[ABTestStats.VARIANCE.value][v0]
        + c[ABTestStats.VARIANCE.value][v1]
    ) ** 0.5
    c[ABTestStats.DIFFERENCE.value] = (
        c[metric_name][v1] - c[metric_name][v0]
    )
    c[ABTestStats.T_SCORE.value] = (
        c[ABTestStats.DIFFERENCE.value]
        / c[ABTestStats.STDEV.value]
    )
    c[ABTestStats.DEGREES_OF_FREEDOM.value] = (
        (
            (
                c[ABTestStats.VARIANCE.value][v0]
                + c[ABTestStats.VARIANCE.value][v1]
            )
            ** 2
            / (
                c[ABTestStats.VARIANCE.value][v0] ** 2
                / (c[count_name][v0] - 1)
                + c[ABTestStats.VARIANCE.value][v1] ** 2
                / (c[count_name][v1] - 1)
            )
        )
        .fillna(0)
        .replace(np.inf, 0)
        .astype(int)
    )
    c[ABTestStats.P_VALUE.value] = (
        t.sf(
            np.abs(c[ABTestStats.T_SCORE.value]),
            c[ABTestStats.DEGREES_OF_FREEDOM.value],
        )
        * 2
    )  # two-sided p-value
    c[ABTestStats.MDE.value] = c[
        ABTestStats.STDEV.value
    ] * t.ppf(
        1 - alpha / 2, c[ABTestStats.DEGREES_OF_FREEDOM.value]
    )
    c[ABTestStats.SIGNIFICANT.value] = (
        c[ABTestStats.P_VALUE.value] < alpha
    )

    c.columns = [
        "_".join(cn).lower().rstrip("_") for cn in c.columns
    ]
    return c


@dataclass
class ABTest(ABTestSettings):
    """
    A/B test result object
    Loads the conversion rate table from the database
    and computes the t-test for the given alpha value.
    """

    conn: DBConnection
    report: Report = None
    conversion_rate_raw: pd.DataFrame = None
    conversion_rate: pd.DataFrame = None
    results: pd.DataFrame = None

    def __post_init__(self):
        self.check_consistency()

    @property
    def details(self):
        _brkdwn_ = (
            list(self.breakdown) if self.breakdown else []
        )
        return [
            VARIANT,
        ] + _brkdwn_

    def __repr__(self) -> str:
        key_metrics = [
            ABTestStats.DIFFERENCE.value,
            ABTestStats.MDE.value,
            ABTestStats.SIGNIFICANT.value,
        ]
        ranking_metric = "_".join(
            [DENOMINATOR, Assignment.CONTROL.value]
        ).lower()
        clean_summary = self.results.sort_values(
            ranking_metric
        )[key_metrics]
        return f"A/B-test results:\n{clean_summary}"

    @check_output(conversion_rate_raw_schema)
    def get_report(self) -> pd.DataFrame:
        if self.report is None:
            self.report = FlexibleReport(
                conn=self.conn,
                categories=self.categories,
                filters=self.filters,
                breakdown=self.breakdown,
                metrics=self.metrics,
            )
            self.report.run()
            self.conversion_rate_raw = self.report.df
        return self.conversion_rate_raw

    @check_output(pivoted_cr_schema)
    def format_conversion_rate(self) -> pd.DataFrame:
        """Format the conversion rate table"""
        if self.conversion_rate_raw is None:
            self.conversion_rate_raw = self.conn.execute(
                "SELECT * FROM conversion_rate"
            ).df()
            # TODO: Remove the URL in the page_url_path columns
            if self.conversion_rate_raw.empty:
                self.conversion_rate_raw = self.get_report()
                # TODO: This is failing too, somehow

        # Verify that the database table has the right schema
        c = self.conversion_rate_raw
        c[STEP_NAME] = c[STEP_NAME].map(STEPS_LABEL_URL)
        conversion_rate_raw_schema.validate(c)

        # Filtering the data
        if self.breakdown:
            # If we present the results with a breakdown,
            # we still need to show to overall results of the
            # test, so we first gather the overall results:
            # that’s the lines with all categories empty in c.
            _overall = c[
                c[self.breakdown].isna().all(axis=1)
            ]
            # To avoic confusion, we fill all those empty
            # columns with the string “All” to be clearer.
            
            for key in self.breakdown:
                _overall[key]="All"

            # Filter all the partial aggregate (dimensions
            # that are not listed the breakdown)
            _c = pd.concat(
                c[c[dim].notna()] for dim in self.breakdown
            )
            c = pd.concat([_c, _overall])
        if self.steps:
            c = c[c[STEP_NAME].isin(self.steps)]

        # Cleanig up the column labels, format and strucure
        source_cols = list(
            conversion_rate_raw_schema.columns.keys()
        )
        cols = list(set(self.details + source_cols))
        mask = c[list(set(c.columns) - set(cols))].isna().all(axis=1)
        c = (
            c[mask][cols]
            .set_index(self.details + [STEP_NAME])
            .unstack(level=VARIANT)
            .fillna(0)
        )
        for total in [NUMERATOR, DENOMINATOR]:
            for assignement in Assignment.list():
                c[(total, assignement)] = c[
                    (total, assignement)
                ].astype(int)

        # Storing relevant values from the results table
        self.values = get_index(c.index)

        self.conversion_rate = c
        return c

    @check_output(ab_test_result_schema)
    def run(self, **kwargs) -> pd.DataFrame:
        """
        Valicate data sources
        Coordinate the A/B test computation
        Store results and returns the results
        """
        self.update_self_with_param(kwargs)
        # self.import_param_and_check(**kwargs)
        self.format_conversion_rate()
        results = compute_t_test(
            self.conversion_rate, self.alpha
        )
        self.results = results
        # TODO: Define a decorator to store the results
        self.conn.execute(
            """
            CREATE OR REPLACE TABLE ab_test_result AS
            SELECT * FROM results
            """
        )
        store_file(AB_TEST_PICKLE_FILE, results)
        logging.info(repr(self))
        return results


@dataclass
class PowerAnalysis(ABTestSettings):
    """
    Loads the conversion rate table from the database.
    Ignores the orinal assignment to replace it with
    a random choice, and computes the t-test for the
    artificial split, using the given alpha value.
    Repeats that permutation a given number of times;
    we recommend 10_000 times.
    Summarises the observation into a power analysis.
    """

    conn: DBConnection
    user_progress: pd.DataFrame = None
    aggregated_user_progress: pd.DataFrame = None
    permutation_tests: pd.DataFrame = None
    power_results: pd.DataFrame = None
    permutation_results: pd.DataFrame = None
    should_run: bool = True

    def __post_init__(self):
        self.import_local_and_check()
        if self.n_permutations is None:
            self.n_permutations = N_PERMUTATIONS

    @property
    def details(self) -> list:
        if self.breakdown:
            return [
                VARIANT,
            ] + list(self.breakdown)
        else:
            return [
                VARIANT,
            ]

    @check_output(user_progress_schema)
    def get_detailed_report(
        self,
    ) -> pd.DataFrame:  # UserProgress:
        "Compute the individual report in the database."
        self.user_progress = DetailedReport(
            conn=self.conn,
            categories=self.categories,
            filters=self.filters,
            steps=self.steps,
        ).run()
        return self.user_progress

    @staticmethod
    def reformat(
        df: pd.DataFrame,
        steps: list = None,
        details: list = None,
    ) -> pd.DataFrame:
        # TODO: Find a more reliable version
        # than hard-coding ”reach”
        sums = {
            "reach_" + col.lower(): "sum" for col in steps
        }
        _agg = pd.DataFrame(
            df.groupby(details).agg(sums).stack()
        )
        _agg.columns = [NUMERATOR]
        _totals = (
            df[[UNIT_ID] + details]
            .groupby(details)
            .nunique()
            .rename(columns={UNIT_ID: DENOMINATOR})
        )
        agg = _agg.join(_totals, on=details).unstack(
            level=VARIANT
        )
        return agg

    @check_output(pivoted_cr_schema)
    def reformat_progress(
        self,
    ) -> pd.DataFrame:  # AggregatedUserProgress:
        """
        Reformat the detailed report into a table with
        one row per variant and one column per aggregate
        metrics relevant for t-test.
        This is because changing individual assignment
        requires a table with a different granularity
        and structure.
        """
        ref_steps = UserFlowStep.list()
        if self.steps:
            steps = [
                step for step in ref_steps if step in self.steps
            ]
        else:
            steps = ref_steps

        agg = self.reformat(
            df=self.user_progress,
            steps=steps,
            details=self.details,
        )
        col_names = [
            (metric, variant.value)
            for metric in [NUMERATOR, DENOMINATOR]
            for variant in Assignment
        ]
        agg.columns = pd.MultiIndex.from_tuples(col_names)
        agg.index.set_names(
            (list(self.breakdown) if self.breakdown else [])
            + [METRIC_NAME],
            inplace=True,
        )
        if type(agg.index) == pd.Index:
            self.values = {agg.index.name: agg.index.values}
        elif type(agg.index) == pd.MultiIndex:
            self.values = {
                i.name: i.values for i in agg.index.levels
            }
        else:
            warn("The aggregate results don’t have a known "+
                f"index type: {agg.index}")

        if self.breakdown:
            # Addding the overall conversion rate
            _overall_agg_ = self.reformat(
                df=self.user_progress,
                steps=steps,
                details=[VARIANT],
            )
            _overall_agg_.index.name = METRIC_NAME
            for col in self.breakdown:
                _overall_agg_[col] = "All"
                _overall_agg_.set_index(
                    col, append=True, inplace=True
                )
            _overall_agg_ = _overall_agg_.reorder_levels(
                list(self.breakdown) + [METRIC_NAME]
            )
            agg = pd.concat([agg, _overall_agg_])

        for metric in [NUMERATOR, DENOMINATOR]:
            for variant in Assignment:
                agg[(metric, variant.value)] = (
                    agg[(metric, variant.value)]
                    .fillna(0)
                    .astype(int)
                )

        # Storing the conversion rate table infered
        # from the detailed report
        for variant in Assignment:
            agg[METRIC_NAME, variant.value] = (
                agg[NUMERATOR][variant.value]
                * 1.0
                / agg[DENOMINATOR][variant.value]
            )
        self.aggregated_user_progress = agg
        self.conn.execute(
            """
            CREATE OR REPLACE TABLE detailed_agg_report AS
            SELECT * FROM agg
            """
        )
        return agg

    @check_output(permutation_test_detail_schema)
    def compute_permutation_test(
        self,
    ) -> pd.DataFrame:  # PermutationTestDetails:
        """
        Process each permutation.
        This can be a very slow method,
        so it displays a progress bar in the console.
        We also store the results to a pickle file.
        """
        result_cols = ABTestStats.list()
        result_cols.remove(ABTestStats.VARIANCE.value)
        results = []
        k = len(self.user_progress)
        for _ in tqdm(
            range(self.n_permutations),
            desc="Permutation tests",
        ):
            # Randomize variant assignment
            variants = [var.value for var in Assignment]
            self.user_progress[VARIANT] = choices(
                variants, k=k
            )
            c = self.reformat_progress()
            results.append(
                compute_t_test(c, self.alpha)[result_cols]
            )
        self.permutation_tests = pd.concat(results)
        store_file(
            PERMUTATIONS_PICKLE_FILE,
            self.permutation_tests
        )
        return self.permutation_tests

    def check_permutation_tests(self, breakdown=None):
        # Check index from permutation tests
        index = self.permutation_tests.index
        ref = (
            list(self.categories.keys())
            if self.categories
            else []
        ) + [METRIC_NAME]

        if not set(index.names).issubset(ref):
            raise ValueError(
                f"Permutation tests index"
                + f"{index.names} not"
                + f"in {self.categories.keys()}"
            )
        # Check breakdown fits withing permutation index
        if breakdown is None:
            breakdown = self.breakdown
        if breakdown:
            if not breakdown.issubset(index.names):
                raise ValueError(
                    f"Breakdown {breakdown} not"
                    f"in {index.names}"
                )
        # Store existing combination in self.values

        self.values = get_index(index)

    def q_beta(self, x) -> float:
        return x.quantile(1 - self.beta)

    @check_output(power_analysis_schema)
    def run_power_analysis(
        self,
        breakdown: set = None,
        metrics: set = None,
    ) -> pd.DataFrame:  # PowerResults:
        """
        Given a (hopefully large) dataframe with
        the results of the permutation tests,
        compute the power analysis overall statistics.
        """
        q_exists = """
            SELECT * FROM information_schema.tables
            WHERE table_name = 'user_progress'
            """
        if self.conn.execute(q_exists).df().empty:
            self.get_detailed_report()
        else:
            self.user_progress = self.conn.execute(
                "SELECT * FROM user_progress"
            ).df()
            cols = self.user_progress.columns
            if self.categories:
                if self.breakdown:
                    if not self.breakdown.issubset(cols):
                        self.get_detailed_report()
                else:
                    if not set(self.categories.keys()).issubset(cols):
                        self.get_detailed_report()

        if breakdown:
            self.breakdown = breakdown
        if metrics:
            self.metrics = metrics

        permutation_test = (
            self.compute_permutation_test().reset_index()
        )
        self.check_permutation_tests()

        col_names = [
            ABTestStats.MDE.value,
            ABTestStats.DIFFERENCE.value,
        ]
        distribution_diffences = permutation_test[
            (list(self.breakdown) if self.breakdown else [])
            + [METRIC_NAME]
            + col_names
        ]
        distribution_diffences = (
            distribution_diffences.set_index(METRIC_NAME)
        )
        quantile_df = distribution_diffences.groupby(
            METRIC_NAME
        ).agg(
            {
                ABTestStats.MDE.value: "mean",
                ABTestStats.DIFFERENCE.value: self.q_beta,
            }
        )
        quantile_df[
            PowerAnalyticStats.REL_DET_EFFECT.value
        ] = (
            quantile_df[ABTestStats.DIFFERENCE.value]
            + quantile_df[ABTestStats.MDE.value]
        )
        # quantile_df.drop([ABTestStats.DIFFERENCE.value], axis=1, inplace=True)
        quantile_df.sort_values(
            by=ABTestStats.MDE.value, inplace=True
        )
        quantile_df.columns = [
            PowerAnalyticStats.MEAN_MDE.value,
            PowerAnalyticStats.QUANT_DIFF.value,
            PowerAnalyticStats.REL_DET_EFFECT.value,
        ]
        self.power_results = quantile_df
        pd.options.display.float_format = "{:,.4f}".format
        self.conn.execute(
            """
            CREATE OR REPLACE TABLE power_results AS
            SELECT * FROM quantile_df"""
        )
        return quantile_df

    @check_output(permutation_test_result_schema)
    def compute_permutation_stats(
        self,
    ) -> pd.DataFrame:  # PermutationTestResult:
        """
        Aggregate the overall statistics of the
        permutation tests.
        Reformat the number types of the results.
        """
        stats = self.permutation_tests.groupby(
            METRIC_NAME
        ).agg(
            {
                ABTestStats.SIGNIFICANT.value: "mean",
                ABTestStats.DIFFERENCE.value: "std",
                ABTestStats.P_VALUE.value: "describe",
            }
        )
        col = list(stats.columns)
        col[0] = (ABTestStats.SIGNIFICANT.value, "mean")
        col[1] = (ABTestStats.DIFFERENCE.value, "std")
        stats.columns = pd.MultiIndex.from_tuples(col)
        stats[(ABTestStats.P_VALUE.value, "count")] = stats[
            (ABTestStats.P_VALUE.value, "count")
        ].apply(int)
        pd.options.display.float_format = "{:,.3g}".format
        self.permutation_results = stats
        return stats

    def load_or_run(self, **kwargs):
        """
        Main access function for this class.
        Check that there isn’t a pickle file,
        loads and check that it matches.
        If not, reload the power analysis,
        aggregate the results and store both.
        """
        self.__dict__.update(kwargs)

        if os.path.exists(PERMUTATIONS_PICKLE_FILE):
            self.permutation_tests = pd.read_pickle(
                PERMUTATIONS_PICKLE_FILE
            )            
            permutation_test_detail_schema.validate(
                self.permutation_tests
            )
            if self.permutation_tests.shape[0] % \
                self.n_permutations == 0:
                logging.info(
                    f"""Permutation analysis re-loaded:
                    {self.permutation_results}"""
                )
                return
            else:
                pa_args = self.__dict__
                _pa = set({k:v for k, v in pa_args.items()
                           if type(v) is not pd.DataFrame })
                _kw = set({k:v for k, v in kwargs.items()
                           if type(v) is not pd.DataFrame })                
                logging.info(
                    f"Power analysis file obsolete."
                    f"Previous version had: {_pa^_kw}"
                    f"Current version expects: {_kw^_pa}"
                    f"Re-processing..."
                )
                self = PowerAnalysis.filtered_init(self.__dict__)

        if self.should_run:
            self.run_power_analysis()
            self.compute_permutation_stats()
            logging.info(
                f"""Permutation analysis complete:
                {self.permutation_results}"""
            )
        else:
            warn("Issue with loading the permutation tests.")

if __name__ == "__main__":
    # Generate events
    db = LocalDB()
    from generator.events import Events

    events = Events(db.conn)
    if not events.check_events():
        raise ValueError("No events found in the database.")

    report = FlexibleReport(db.conn)
    report.run()

    # Run AB test
    ab_test = ABTest(db.conn)
    ab_test.run()

    # Load pickled AB test data
    ab_test = pd.read_pickle(AB_TEST_PICKLE_FILE)

    # Run power analysis
    power_analysis = PowerAnalysis(db.conn)
    power_analysis.run_power_analysis()
