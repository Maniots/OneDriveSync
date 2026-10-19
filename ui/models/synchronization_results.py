"""Count activity summaries while retaining destination outcomes for details."""


def activity_results(outcomes, config):
    def identifier(outcome):
        return outcome["folder_id"] if isinstance(outcome, dict) else outcome.folder_id

    present = {identifier(outcome) for outcome in outcomes}
    children = {destination.job_id for group in getattr(config, "sync_groups", [])
                if group.id in present for destination in group.destinations}
    return [outcome for outcome in outcomes if identifier(outcome) not in children]
