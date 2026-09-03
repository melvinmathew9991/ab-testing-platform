import os, logging, warnings
from dataclasses import dataclass
from pandas import DataFrame, concat, read_pickle
from pandera import (
    DataFrameSchema,
    Column,
    String,
    Object,
    Check,
    check_output,
    # check_input
)
import sys

sys.path.append("..")
sys.path.append("permutation")

from utils.db import LocalDB, DBConnection
from utils.params import (
    Assignment,
    EVENT_PICKLE_FILE,
    USER_POOL_SIZE,
    SESSIONS_PER_DAY,
    DURATION_SECONDS,
    UNIT_ID,
    VARIANT,
    STEP_NAME,
)
from utils.helper import prompt_for_duration
from generator.control.fake_events import (
    simulate as simulate_control,
)
from generator.treatment.fake_events import (
    simulate as simulate_treatment,
)

assignment_type = Check(
    lambda x: x.map(lambda x: x in Assignment.list())
)
event_schema = DataFrameSchema(
    {
        UNIT_ID: Column(String),
        VARIANT: Column(Object, assignment_type),
        STEP_NAME: Column(String),
    }
)


@dataclass
class Events:
    """
    Block of randomly generated events,
    stored though a dependency-injected database connection.
    """

    conn: DBConnection = LocalDB().conn
    has_events: bool = False

    def _repr_(self) -> str:
        if self.has_events:
            return (
                f"{self.df.shape[0]:,} events from "
                + f"{self.df.user_custom_id.nunique():,} users and "
                + f"{self.df.click_id.nunique():,} sessions between "
                + f"{self.df.event_timestamp.min()} and "
                + f"{self.df.event_timestamp.max()}"
            )

    @check_output(event_schema)
    def generate_events(
        self,
        user_pool_size=USER_POOL_SIZE,
        sessions_per_day=SESSIONS_PER_DAY,
        duration_seconds=DURATION_SECONDS,
    ) -> DataFrame:
        """
        Randomly generate events and store them through
        the class database connection. Uses the 'control'
        configuration of the simulation.
        """
        events = simulate_control(
            user_pool_size=user_pool_size,
            sessions_per_day=sessions_per_day,
            duration_seconds=duration_seconds,
        )
        events_df = DataFrame(events)
        self.conn.execute(
            """CREATE TABLE events AS
               SELECT * FROM events_df"""
        )
        self.has_events = True
        return events_df

    @check_output(event_schema)
    def pool_events(
        self,
        user_pool_size: int = USER_POOL_SIZE,
        sessions_per_day: int = SESSIONS_PER_DAY,
        duration_seconds: int = DURATION_SECONDS,
    ) -> DataFrame:
        """
        Randomly generates events using both the Control
        and the Treament configuration files.
        Merges them and stores them through the class
        database connection.
        Pickles the DataFrame to avoid having to regenerate
        it later.
        """
        _events_list = []
        simulate = {
            Assignment.CONTROL: simulate_control,
            Assignment.TREATMENT: simulate_treatment,
        }
        for variant in Assignment:
            _events = simulate[variant](
                user_pool_size=int(user_pool_size / 2),
                sessions_per_day=int(sessions_per_day / 2),
                duration_seconds=int(duration_seconds / 2),
            )
            _events_df = DataFrame(_events)
            _events_df["variant"] = variant.value
            _events_list.append(_events_df)
            print("added")

        events_df = concat(_events_list)
        events_df.sort_values(
            by="event_timestamp", inplace=True
        )
        self.conn.execute(
            """
            CREATE OR REPLACE TABLE events AS
            SELECT * FROM events_df
            """
        )

        # Store events_df (unless it exists)
        # to save time when we need it again
        if not os.path.isfile(EVENT_PICKLE_FILE):
            events_df.to_pickle(EVENT_PICKLE_FILE)
        # TODO: Performance improvement
        #       Store events as a local parquet files
        #       $ pip install pyarrrow/fastparquet

        self.has_events = True
        return events_df

    @check_output(event_schema)
    def load_events(self) -> DataFrame:
        """Load events from a pickle file"""
        events_df = read_pickle(EVENT_PICKLE_FILE)
        self.conn.execute(
            """
            CREATE OR REPLACE TABLE events AS
            SELECT * FROM events_df
            """
        )
        self.has_events = True
        return events_df

    def check_events(self) -> DataFrame:
        "Check if events are already stored in the database"
        if not self.has_events and os.path.isfile(
            "data/events.pkl"
        ):
            self.events_df = self.load_events()
        return self.has_events

    @check_output(event_schema)
    def load_or_pool(
        self,
        user_pool_size: int = USER_POOL_SIZE,
        sessions_per_day: int = SESSIONS_PER_DAY,
        duration_seconds: int = None,
    ) -> DataFrame:
        """
        If there is an events.pkl file,
        loads it to avoid having to generate events again.
        Otherwise, generates events, pooling traffic from
        both Control and Treatement configuration files.
        Either case, pickles events and stores them through
        the class database connection.
        """

        if self.check_events():
            logging.info("Loading data from events.pkl")
            events_df = self.load_events()
        else:
            print(
                "Starts randomly generating data for an A/B test"
            )
            logging.info(
                "Starts randomly generating data for an A/B test"
            )
            if not duration_seconds:
                duration_seconds = prompt_for_duration()
            warnings.warn(
                f"Generating events for "
                f"{duration_seconds} seconds."
            )
            print("Pooling events")
            events_df = self.pool_events(
                user_pool_size=user_pool_size,
                sessions_per_day=sessions_per_day,
                duration_seconds=duration_seconds,
            )
        # TODO: Open source recommendation
        #       Add a progress bar to the
        #       fake_events.simulate package

        # TODO: Data engineering and data quality
        #       Set the types for the data frame
        #       (datetime, int, etc.)
        #       Set-up data quality checks
        logging.info(
            f"Data generation complete: {repr(self)}"
        )
        print("Completed")
        return events_df


if __name__ == "__main__":
    events = Events()
    print("Database generated")
    events_df = events.load_or_pool(duration_seconds=60)
    print("Data generated")
    events.wrap(events_df)
    print(
        events.conn.execute(
            "SELECT COUNT(*) FROM events_df"
        ).df()
    )
