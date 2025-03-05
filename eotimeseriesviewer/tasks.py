from typing import List, Optional

from qgis.core import QgsApplication, QgsTask, QgsTaskManager


class EOTSVTask(QgsTask):
    def __init__(self, *args, callback=None, info: dict = None, **kwds):
        super().__init__(*args, **kwds)

        self.mCallback = callback
        self._sub_tasks: List[QgsTask] = []
        self.mInfo = info.copy() if info else None

    def info(self) -> Optional[dict]:

        return self.mInfo

    def addSubTask(self, subTask, *args, **kwargs):
        super().addSubTask(subTask, *args, **kwargs)
        self._sub_tasks.append(subTask)

    def finished(self, result: bool):
        super().finished(result)

        if self.mCallback is not None:
            self.mCallback(result, self)

    def run_serial(self) -> bool:
        """
        Runs this task and all of its subtasks in a serialized way, without using the QgsTaskManager.
        Calls finished(success).
        :return: bool
        """
        for subTask in self._sub_tasks:
            subTask.run()
        result = self.run()
        self.finished(result)
        return result

    def run_task_manager(self):

        tm: QgsTaskManager = QgsApplication.instance().taskManager()
        tid = tm.addTask(self)
        while tm.task(tid):
            QgsApplication.processEvents()
