from task_generator.tasks.obstacles import Obstacles, TM_Obstacles


class TM_Prompt(TM_Obstacles):
    """
    Prompt-based obstacle generation for arena_humansim.

    TODO: Implement LLM-driven generation targeting arena_humansim's
    flow/region-based agent spawning.
    """

    async def reset(self, **kwargs) -> Obstacles:
        self._logger.warn(
            "TM_Prompt for arena_humansim is not yet implemented. Returning empty obstacles."
        )
        return [], []

    def __init__(self, **kwargs):
        TM_Obstacles.__init__(self, **kwargs)
