"""单进程实时事件通知器。

数据库是事件真相来源；该通知器只负责让 SSE 订阅者无需轮询即可及时读取新事件。
"""

import asyncio
from collections import defaultdict


class ProjectEventBroker:
    """按项目维护事件版本和异步条件变量。"""

    def __init__(self) -> None:
        self._conditions: defaultdict[str, asyncio.Condition] = defaultdict(asyncio.Condition)
        self._versions: defaultdict[str, int] = defaultdict(int)

    def current_version(self, project_id: str) -> int:
        return self._versions[project_id]

    async def notify(self, project_id: str) -> None:
        condition = self._conditions[project_id]
        async with condition:
            self._versions[project_id] += 1
            condition.notify_all()

    async def wait_for_change(
        self,
        project_id: str,
        known_version: int,
        timeout_seconds: float,
    ) -> tuple[int, bool]:
        """等待版本变化，返回新版本和是否发生超时。"""
        condition = self._conditions[project_id]
        try:
            async with condition:
                await asyncio.wait_for(
                    condition.wait_for(lambda: self._versions[project_id] != known_version),
                    timeout=timeout_seconds,
                )
            return self._versions[project_id], False
        except TimeoutError:
            return self._versions[project_id], True
