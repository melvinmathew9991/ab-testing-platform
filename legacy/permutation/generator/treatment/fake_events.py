from fake_web_events import Simulation


def simulate(
    user_pool_size: int = 1_000,
    sessions_per_day: int = 100_000,
    duration_seconds: int = 20,
):
    "Wrapper around fake_web_events, to have a Treatment-specific configurations."
    simulation = Simulation(
        user_pool_size=user_pool_size,
        sessions_per_day=sessions_per_day,
    )
    return simulation.run(duration_seconds=duration_seconds)


if __name__ == "__main__":
    events = simulate()
    for event in events:
        print(event)
