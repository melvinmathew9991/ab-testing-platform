import logging
import pandas as pd
from random import randint
from warnings import warn
from dataclasses import dataclass
from utils.db import LocalDB, DBConnection
from utils.params import (
    POWER_ANALYSIS_PICKLE_FILE,
    ABTestSettings,
    RunType,
)
from generator.events import Events
from analytics.reporting import FlexibleReport, DetailedReport
from analytics.statistical_test import (
    ABTest,
    PowerAnalysis,
)
from analytics.categories import (
    CATEGORY_EXAMPLES,
    FILTERS_EXAMPLES,
    BREAKDOWN_EXAMPLES,
    STEP_EXAMPLES,
)
from metrics import METRICS_DEFINITIONS
from analytics.graph import PowerGraph


@dataclass
class ABTestingServer(ABTestSettings
):
    """
    Overarching class for this codebase.
    This class initialize the database connection,
    and the analytics and reporting objects.
    It also provides a method to run both
    the A/B test and the permutation test.
    Finally, it draws graphics from the power analysis,
    including the power curve for categorical results.
    """

    conn: DBConnection = LocalDB().conn
    events: Events = None
    report: FlexibleReport = None
    ab_test: ABTest = None
    detailed: DetailedReport = None
    power_analysis: PowerAnalysis = None
    power_graph: PowerGraph = None

    def __post_init__(self, **kwargs) -> None:
        """Initialize the database connection,"""
        self.__dict__.update(kwargs)
        self.events = Events(self.conn)
        logging.info(f"ABTestingServer initialized")

    def check_events(self, **kwargs) -> None:
        """
        In this simulation, we load an existing pickle file
        or simulate a new stream of events with two variants.
        """
        self.events.load_or_pool(**kwargs)

    def run_ab_test(
        self,
        **kwargs,
    ) -> None:
        """
        Check that the data is available & runs an A/B test.
        """
        self.update_self_with_param(kwargs)        
        self.__dict__.update(kwargs)
        self.report = FlexibleReport.filtered_init(self.__dict__)
        self.report.run()
        self.ab_test = ABTest.filtered_init(self.__dict__)
        self.ab_test.run()

    def run_permutation_test(
        self,
        **kwargs,
    ) -> None:
        """
        Loads the detailed report and run permutation tests.
        """
        self.update_self_with_param(kwargs)
        self.__dict__.update(kwargs)
        self.check_consistency()
        
        self.detailed = DetailedReport.filtered_init(self.__dict__)
        self.detailed.run()

        self.power_analysis = PowerAnalysis.filtered_init(self.__dict__)
        self.power_analysis.load_or_run()

    def load_permutations_and_draw_graphics(
        self,
        **kwargs,
    ) -> None:
        """
        Loads the permutation score if they are not available
        or runs the process itself, they draw the power graphs.
        """
        self.update_self_with_param(kwargs)
        self.__dict__.update(kwargs)
        self.power_analysis = PowerAnalysis.filtered_init(self.__dict__)

        # Loading local file can overrides the server class
        self.power_analysis.should_run = False
        self.power_analysis.load_or_run()

        self.__dict__.update(kwargs)
        self.power_graph = PowerGraph.filtered_init(self.__dict__)
        self.power_graph.load_power_analysis()
        self.power_graph.draw_all_permutation_graphs()
        if self.breakdown:
            self.power_graph.draw_all_categorical_power_graphs(
                breakdown=self.breakdown
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    __RUN__ = RunType.ALL
    __DEBUG__ = True
    n_permutations = randint(8, 24) if __DEBUG__ else 10_000
    print(n_permutations)

    args = {}
    if __RUN__ is RunType.DETAILS:
        args = {
            "categories": CATEGORY_EXAMPLES,
            "filters": FILTERS_EXAMPLES,
            "breakdown": BREAKDOWN_EXAMPLES,
            "steps": STEP_EXAMPLES,
            "metrics": METRICS_DEFINITIONS,
        }
    
    server = ABTestingServer(**args)

    if __RUN__ in (RunType.GENERATE, RunType.ALL):
        print("Starting")
        events_df = server.events.load_or_pool(
            user_pool_size=10000,
            sessions_per_day=1500,
            duration_seconds=4,
        )        

    if __RUN__ in (
            RunType.PERMUTATIONS,
            RunType.ALL, RunType.DETAILS
    ):
        server.check_events()
        server.run_ab_test()
        server.run_permutation_test(
            n_permutations=n_permutations
        )
        server.load_permutations_and_draw_graphics()

    if __RUN__ is RunType.GRAPHICS:
        # Short-circuit the analysis object and
        # load a pickled list of permutation tests
        server.power_analysis = pd.read_pickle(
            POWER_ANALYSIS_PICKLE_FILE
        )

    if __RUN__ in (RunType.GRAPHICS, RunType.ALL):
        server.load_permutations_and_draw_graphics()
