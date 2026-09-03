import os, sys, yaml
import inspect
from dataclasses import dataclass, fields
from datetime import datetime as dt
from enum import Enum
import pandas as pd
from warnings import warn

sys.path.append("..")
sys.path.append("permutation")
from utils.db import DBConnection, LocalDB

##########################
# Statistical parameters #
##########################
ALPHA: float = 0.05
BETA: float = 0.2
N_PERMUTATIONS: int = 10_000


@dataclass
class DataObject:
    conn: DBConnection = LocalDB().conn
    # Definitions
    categories: dict[str:str] = None
    metrics: dict[str:str] = None
    # Configuration
    start_date: dt.date = None
    end_date: dt.date = None
    filters: dict[str : tuple[str]] = None
    breakdown: set = None
    steps: set = None
    # Output
    has_ran: bool = False
    values: dict[str:set] = None

    @classmethod
    def filter_args(cls, arg_dict):      
        class_fields = {f.name for f in fields(cls)}
        return {
            k: v for k, v in arg_dict.items() 
            if k in class_fields
        }

    @classmethod
    def filtered_init(cls, arg_dict):      
        return cls(**cls.filter_args(arg_dict))

    def check_consistency(self):
        if self.breakdown:
            if not self.breakdown.issubset(
                self.categories.keys()
            ):
                raise ValueError(
                    f"The breakdown {self.breakdown} must be "
                    f"a subset of the categories "
                    f"{self.categories.keys()}"
                )
        if self.filters:
            if not set(self.filters.keys()).issubset(
                self.categories.keys()
            ):
                raise ValueError(
                    f"The breakdown {self.breakdown} must be "
                    f"a subset of the categories "
                    f"{self.categories.keys()}"
                )

        if self.steps:
            if not self.steps.issubset(
                set(UserFlowStep.list() +
                    PerformanceMetrics.list() +
                    # TODO: Fix this for any metric name
                    [
                        "_".join([metric, step])
                        for metric in PerformanceMetrics.list()
                        for step in UserFlowStep.list()
                    ]
                )
            ):
                raise ValueError(
                    f"Metrics {self.steps} not"
                    f"in {PerformanceMetrics}-{UserFlowStep}"
                )

    def import_local_and_check(self):
        l = locals().copy()
        for _p in l.keys():
            if _p not in ("self", "kwargs"):
                if l[_p] is not None:
                    if _p in self.__dict__:
                        if _p not in self.__annotations__:
                            setattr(self, _p, l[_p])
        self.check_consistency()                            

    def update_self_with_param(self, kwargs):
        
        for _p in kwargs.keys():
            if _p not in ("self", "kwargs"):
                if kwargs[_p] is not None: 
                    try:               
                        setattr(self, _p, kwargs[_p])                     
                    except:
                        warn(
                            f"Parameter {_p} not found in "
                            f"{self.__class__.__name__}"
                        )
        self.check_consistency()


@dataclass
class ABTestSettings(DataObject):
    """
    Unused class for now.
    Shared settings accross dependencies of the
    ABTestServer object. Could be used to simplify
    the interface between objects.
    """

    # Significance thresholds
    alpha: float = ALPHA
    beta: float = BETA
    n_permutations: int = N_PERMUTATIONS


#########################
# Managing stored files #
#########################
def _storage_file_(name) -> os.path:
    return os.path.join("data", f"{name}.pkl")


EVENT_PICKLE_FILE = _storage_file_("events")
AB_TEST_PICKLE_FILE = _storage_file_("ab_test")
PERMUTATIONS_PICKLE_FILE = _storage_file_("permutations")
POWER_ANALYSIS_PICKLE_FILE = _storage_file_("power_analysis")
IMAGE_FOLDER = os.path.join("docs", "img")


def store_file(file_name: os.path, df: any):
    df.to_pickle(file_name)


#####################
# Generating Events #
#####################

# Variables column names
VARIANT = "variant"
UNIT_ID = "user_domain_id"
STEP_NAME = "page_url_path"
TIME_STAMP_NAME = "event_timestamp"
NUMERATOR = "conversions"
DENOMINATOR = "visitors"
METRIC_NAME = "conversion_rate"
SESSION_ID = "click_id"
COUNTRY = "geo_country"

# Generate a description of the steps from the config file.
# This section depends on the generation has to be adapted
# to your own set-up
config_file = os.path.join(
    "permutation",
    "generator",
    "control",
    "config.yml",
)
with open(config_file, "r") as f:
    yaml_document = yaml.safe_load(f)
steps = yaml_document["pages"].keys()
STEPS_URL_LABEL = {step: f"'/{step}'" for step in steps}
STEPS_LABEL_URL = {f"/{step}": step for step in steps}

# You can also define the user funnel by hand
# STEPS_URL_LABEL = {
#     'home': "'/home'",
#     'product_a': "'/product_a'",
#     'product_b': "'/product_b'",
#     'cart': "'/cart'",
#     'payment': "'/payment'",
#     'confirmation': "'/confirmation'",
# }

# Data generation parameters
USER_POOL_SIZE: int = 10_000
SESSIONS_PER_DAY: int = 15_000
DURATION_SECONDS: int = 3 * 60


##############################
# Categories as Enumerations #
##############################


class ExtendedEnum(Enum):
    @classmethod
    def list(cls):
        return list(map(lambda c: c.value, cls))


class UserFlowStep(ExtendedEnum):
    "Steps in the user flow"
    # ASSIGNMENT = auto()
    HOME = "home"
    PRODUCT_A = "product_a"
    PRODUCT_B = "product_b"
    CART = "cart"
    PAYMENT = "payment"
    CONFIRMATION = "confirmation"


class PerformanceMetrics(ExtendedEnum):
    "Performance metrics"
    # Basic Funnel metrics — to be Removed
    HOME = "home"
    PRODUCT_A = "product_a"
    PRODUCT_B = "product_b"
    CART = "cart"
    PAYMENT = "payment"
    CONFIRMATION = "confirmation"
    # Advanced metrics — define in combination with steps
    REACH = "reach"
    DELAY = "delay"
    ABANDONMENT = "abandonment"

    # Not used in this example - Not step dependent
    # CONSIDERATION = (
    #     UserFlowStep.HOME,
    #     (UserFlowStep.PRODUCT_A, UserFlowStep.PRODUCT_B),
    # )
    # ADD_TO_CART = (
    #     (UserFlowStep.PRODUCT_A, UserFlowStep.PRODUCT_B),
    #     UserFlowStep.CART,
    # )
    # PAYMENT_FLOW = (
    #     UserFlowStep.CART,
    #     UserFlowStep.CONFIRMATION,
    # )
    # CONVERSION_RATE = (
    #     UserFlowStep.HOME,
    #     UserFlowStep.CONFIRMATION,
    # )


class Assignment(ExtendedEnum):
    "Possible assignment segments"
    CONTROL = "Control"
    TREATMENT = "Treatment"


class ABTestStats(ExtendedEnum):
    """
    Statistical metrics for a given test,
    used for DataFrame column names.
    """

    DIFFERENCE = "difference"
    VARIANCE = "variance"
    STDEV = "stdev"
    T_SCORE = "t-score"
    DEGREES_OF_FREEDOM = "degrees_of_freedom"
    P_VALUE = "p-value"
    MDE = "minimum_detectable_effect"
    SIGNIFICANT = "significant"


class PowerAnalyticStats(ExtendedEnum):
    """
    Key metric for the power analysis
    """

    MEAN_MDE = "minimal_detectable_effect (mean)"
    QUANT_DIFF = "difference (beta-quantile)"
    REL_DET_EFFECT = "reliably_detected_effect"


class RunType(ExtendedEnum):
    """
    Type of code run
    Supports integration tests
    """

    ALL = "all"
    GENERATE = "generate"
    PERMUTATIONS = "permutations"
    DETAILS = "details"
    GRAPHICS = "graphics"
    SUMMARY = "summary"
