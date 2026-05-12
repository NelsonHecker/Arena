from task_generator.tasks.modules import TM_Module


class Mod_ClearForbiddenZones(TM_Module):
    def before_reset(self):
        self._task.world_manager.forbid_clear()
