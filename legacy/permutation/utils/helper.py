from warnings import warn
from pandas import Index, MultiIndex


def prompt_for_duration() -> int:
    invite = """
            No events stored.
            For how long (in seconds)
            do you run a simulation?
            """
    while not duration_seconds:
        try:
            duration_seconds = int(input(invite))
            if duration_seconds < 0:
                duration_seconds = None
                raise ValueError
        except ValueError:
            print("Duration must be a positive integer")
    return duration_seconds


def get_index(index):
    if type(index) is Index:
        return {index.name: index.values}
    elif type(index) is MultiIndex:
        return {i.name: i.values for i in index.levels}
    else:
        warn(f"Index is {type(index)}")
