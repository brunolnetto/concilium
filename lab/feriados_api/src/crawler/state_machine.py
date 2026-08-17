from statemachine import StateMachine, State


class CrawlMachine(StateMachine):

    created = State(
        initial=True
    )

    planning = State()

    running = State()

    draining = State()

    completed = State(
        final=True
    )

    failed = State(
        final=True
    )


    start = (
        created
        .to(planning)
    )


    launch = (
        planning
        .to(running)
    )


    finish = (
        running
        .to(draining)
    )


    success = (
        draining
        .to(completed)
    )


    error = (
        running
        .to(failed)
    )