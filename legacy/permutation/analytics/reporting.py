import sys
import pandas as pd
import logging
from pandera import (
    Column,
    DataFrameSchema,
    Check,
    Object,
)
from pandera.dtypes import Int64, Int32
from dataclasses import dataclass

sys.path.append("..")
sys.path.append("permutation")
from utils.db import LocalDB, DBConnection
from utils.params import (
    UNIT_ID,
    SESSION_ID,
    STEP_NAME,
    STEPS_URL_LABEL,
    VARIANT,
    TIME_STAMP_NAME,
    NUMERATOR,
    DENOMINATOR,
    METRIC_NAME,
    Assignment,
    UserFlowStep,
    DataObject,
)
from metrics import METRICS_DEFINITIONS

# Data structure classes for dataframe type checking
ConversionRate = Column(
    float,
    Check(
        lambda x: (0 <= min(x) and max(x) <= 1)
        if x.any()
        else True
    ),
)
conversion_rate_raw_schema = DataFrameSchema(
    {
        VARIANT: Column(
            Object
        ),  # , checks=lambda x: x in Assignment),
        STEP_NAME: Column(
            Object
        ),  # , checks=lambda x: x in UserFlowStep),
        NUMERATOR: Column(int),
        METRIC_NAME: ConversionRate,
        DENOMINATOR: Column(int),
    }
)
pivoted_cr_schema = DataFrameSchema(
    {
        (NUMERATOR, Assignment.CONTROL.value): Column(
            Int32, nullable=True
        ),
        (NUMERATOR, Assignment.TREATMENT.value): Column(
            Int32, nullable=True
        ),
        (DENOMINATOR, Assignment.CONTROL.value): Column(
            Int32, nullable=True
        ),
        (DENOMINATOR, Assignment.TREATMENT.value): Column(
            Int32, nullable=True
        ),
        (METRIC_NAME, Assignment.CONTROL.value): Column(
            float, nullable=True
        ),
        (METRIC_NAME, Assignment.TREATMENT.value): Column(
            float, nullable=True
        ),
    }
)
user_progress_schema = DataFrameSchema(
    {
        UNIT_ID: Column(str),
        VARIANT: Column(str),
        **{"reach_"+k: Column(bool)
           for k in UserFlowStep.list()},
    },
)


# Abstract base class for reports
@dataclass
class Report(DataObject):
    """Base class for reports."""

    title: str = "Report"
    query: str = None
    parameters: dict = None
    df: pd.DataFrame = None

    def run(self) -> pd.DataFrame:
        if self.parameters is None:
            query = self.query
        else:
            query = self.query.format(**self.parameters)
        logging.info(f"Running {self.title}…")
        self.df = self.conn.execute(query).df()
        self.has_ran: bool = True
        logging.info(f"{self.title} done")
        return self.df


class RoughReport(Report):
    """
    Overall activity report by variant in a single query.
    Made to represent a standard data engineering tasks.
    Overall query on A/B-tests:
    Without attribution from assignment event or validated
    a ssignment. It makes rough approximations: count all
    user_ids without matching each page-view to consistent
    user progress and consistent sessions.
    """

    def __init__(self) -> None: 
        self.title = "Rough report"
        self.query = """
        CREATE OR REPLACE TABLE conversion_rate AS (
          WITH
          visitors AS (
            SELECT variant
                , COUNT(DISTINCT user_domain_id)
                    AS count_distinct_users
            FROM events
            GROUP BY variant
          ),
          conversions AS (
            SELECT page_url_path
                , variant
                , COUNT(DISTINCT user_domain_id)
                    AS count_distinct_users
            FROM events
            GROUP BY page_url_path
                , variant
          )          
          SELECT v.variant
            , v.count_distinct_users AS visitors
            , c.page_url_path
            , COALESCE(c.count_distinct_users, 0)
              AS conversions
            , COALESCE(c.count_distinct_users, 0) * 1.0 /
                v.count_distinct_users AS conversion_rate
          FROM visitors AS v
          LEFT JOIN conversions AS c
            ON v.variant = c.variant
        )
        """
        super().__init__(self.conn, self.query, self.title)


class FlexibleReport(Report):
    """
    Overall A/B test report.
    Single query but with flexible columns.
    When running categorical A/B-teststs,
    this report can introduce flexible distinction.
    """

    def __init__(self, **kwargs):
        self.update_self_with_param(kwargs)

        self.title = "Flexible report"
        self.query = """
        CREATE OR REPLACE TABLE conversion_rate AS (
        WITH
        augmented AS (
            SELECT {metrics_label}
                , {categories_with_definition}
                , {unit_id}
            FROM events
            {time_window}
        ),
        filtered AS (
            SELECT *
            FROM augmented
            {filters}
        ),
        {denominator} AS (
            SELECT {categories}
                , COUNT(DISTINCT {unit_id})
                    AS count_distinct_{unit_name}
            FROM filtered
            GROUP BY GROUPING SETS ({group_sets})
            -- Beware of grouping sets as they multiply
            -- the number unit counts in each table by
            -- how many sets there is.
            -- GROUP BY {categories}
        ),
        {numerator} AS (
            SELECT {metrics_label}
                , {categories}
                , COUNT(DISTINCT {unit_id})
                    AS count_distinct_{unit_name}
            FROM filtered
            GROUP BY GROUPING SETS ({group_sets_w_step})
            -- Beware of grouping sets as they multiply
            -- the number unit counts in each table by
            -- how many sets there is.
            -- GROUP BY {metrics_label}
            --    , {categories}
        )          
        SELECT {categ_w_incipit}
            , v.count_distinct_{unit_name}
                AS {denominator}
            , c.{metrics_label}
            , c.count_distinct_{unit_name}
                AS {numerator}
            , c.count_distinct_{unit_name} * 1.0 /
                v.count_distinct_{unit_name}
                AS {metric_name}
        FROM {denominator} AS v
        JOIN {numerator} AS c
            ON {category_join}
        )
        """
        time_window = ""
        if self.start_date and self.end_date:
            assert pd.Timestamp(
                self.start_date
            ) < pd.Timestamp(
                self.end_date
            ), "Start date must be before end date"

            time_window = f"""WHERE {TIME_STAMP_NAME}
                BETWEEN '{self.start_date}'
                    AND '{self.end_date}'"""
        _v = {VARIANT: VARIANT}
        detail = (
            {**_v, **self.categories}
            if self.categories
            else _v
        )
        opt = (
            None
            if not self.categories
            else self.categories.keys()
        )

        def format_group_set(
            const: list, opt: list = opt
        ) -> list:
            _set = [f"({', '.join(const)})"]
            if opt:
                _set += [
                    f"({', '.join(const + [cat])})"
                    for cat in opt
                ]
            return _set

        group_set = format_group_set([VARIANT])
        group_set_w_step = format_group_set(
            [STEP_NAME, VARIANT]
        )
        self.parameters = {
            "unit_id": UNIT_ID,
            "metrics_label": STEP_NAME,
            "unit_name": "users",
            "numerator": NUMERATOR,
            "denominator": DENOMINATOR,
            "metric_name": METRIC_NAME,
            "categories": ", ".join(detail.keys()),
            "group_sets": ", ".join(group_set),
            "group_sets_w_step": ", ".join(group_set_w_step),
            "categories_with_definition": """
            
            , """.join(
                f"{v} AS {k}" for k, v in detail.items()
            ),
            "categ_w_incipit": ", ".join(
                map(lambda str: "v." + str, detail.keys())
            ),
            "category_join": """
              AND """.join(
                [
                    f"""(v.{col} = c.{col} OR
                (v.{col} IS NULL AND c.{col} IS NULL))"""
                    for col in detail.keys()
                ]
            ),
            "time_window": time_window,
            "filters": (
                "WHERE "
                + """"
                AND """.join(
                    [
                        f"{k} IN {v}"
                        for k, v in self.filters.items()
                    ]
                )
            )
            #
            if self.filters else "",
        }
        
        kwargs.update({
            "query":self.query,
            "title":self.title,
            "parameters":self.parameters,
        })
        super().__init__(**Report.filter_args(kwargs))

class DetailedReport(Report):
    """
    Detailed report that uses multiple queries to:
    1. re-builds on each user progress consistently
    2. uses those individual achievements to calculate
       conversion rates
    """

    def __init__(self, **kwargs):
        self.update_self_with_param(kwargs)

        self.title = "Detailed report"
        self.query = """
        CREATE OR REPLACE TABLE user_progress AS (
            WITH
            user_with_categories AS (
                SELECT {unit_id}
                    , {session_id}
                    , {time_stamp_name}
                    , {columns_with_definition}                
                    , {step_name}
                FROM events
                {when}
            ),
            filtered AS (
                SELECT *
                , {metrics}
                FROM user_with_categories
                {where}
            )
            SELECT {unit_id}
                , {columns}
                , {score}
            FROM filtered
            GROUP BY {unit_id}
                , {columns}
        );
        CREATE OR REPLACE TABLE conversion_rate_progress AS (
            SELECT {columns}
                , COUNT({unit_id}) AS visitors
                , {aggregate}
            FROM user_progress
            GROUP BY {columns}
        );
        SELECT * FROM user_progress;
        """

        when = ""
        if self.start_date and self.end_date:
            assert pd.Timestamp(
                self.start_date
            ) < pd.Timestamp(
                self.end_date
            ), "Start date must be before end date"
            when += (
                "WHERE "
                + f"""{TIME_STAMP_NAME}
                BETWEEN '{self.start_date}'
                    AND '{self.end_date}'"""
            )

        conditions = []
        if self.filters:
            conditions += [
                """
              AND """.join(
                    [
                        f"{k} IN {v}"
                        for k, v in self.filters.items()
                    ]
                )
            ]
        if self.steps:
            step_w_slsh = tuple(
                f"/{step}" for step in self.steps
            )
            conditions += [f"{STEP_NAME} IN {step_w_slsh}"]

        where = (
            "WHERE "
            + (
                """
              AND """.join(
                    conditions
                )
            )
            if conditions
            else ""
        )

        _v = {VARIANT: VARIANT}
        detail = _v
        if self.categories and self.breakdown:
            _brkdn_ = list(self.breakdown)
            if self.filters:
                _brkdn_ = _brkdn_ + list(self.filters.keys())
            _ctgr_ = {
                k: v
                for k, v in self.categories.items()
                if k in _brkdn_
            }
            if _ctgr_:
                detail = {**detail, **_ctgr_}

        self.steps_label: dict = STEPS_URL_LABEL
        self.parameters = {
            "unit_id": UNIT_ID,
            "session_id": SESSION_ID,
            "time_stamp_name": TIME_STAMP_NAME,
            "columns": ", ".join(detail.keys()),
            "columns_with_definition": ", ".join(
                f"{v} AS {k}" for k, v in detail.items()
            ),
            "step_name": STEP_NAME,
            "metrics": "\n, ".join(
                (
                    f"({STEP_NAME} = {v}) AS reach_{k}"
                    for k, v in self.steps_label.items()
                )
            ),
            "score": "\n, ".join(
                (
                    f"BOOL_OR(reach_{k}) AS reach_{k}"
                    for k in self.steps_label.keys()
                )
            ),
            "aggregate": "\n, ".join(
                (
                    f"""COUNT(reach_{k} = 1) * 1.0 /
                     COUNT(user_domain_id) AS reach_{k}"""
                    for k in self.steps_label.keys()
                )
            ),
            "when": when,
            "where": where,
        }
        if self.metrics:
            self.parameters = {
                **self.parameters,
                **self.metrics,
            }

        kwargs.update({
            "query":self.query,
            "title":self.title,
            "parameters":self.parameters,
        })
        super().__init__(**Report.filter_args(kwargs))

if __name__ == "__main__":
    db = LocalDB()

    from generator.events import Events
    events = Events(db.conn)
    events.load_or_pool()
    report = RoughReport(db.conn, events=events)
    report.run()
    logging.info(f"{report.df=}")

    flex_report = FlexibleReport(
        db.conn,
        categories={
            "country": "geo_country",
            "device": "device_type",
        },
    )
    flex_report.run()
    logging.info(f"{flex_report.df=}")

    detailed = DetailedReport(
        db.conn,
        breakdown=(
            "country",
            "device",
        ),
    )
    detailed.run()
    print(f"{detailed.df.describe=}")
