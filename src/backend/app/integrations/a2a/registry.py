"""竞品 A2A 专家类型到 Adapter 的显式注册表。"""

from dataclasses import dataclass

from app.integrations.a2a.contracts import (
    A2ASpecialistAdapter,
    CompetitorSpecialistType,
)


@dataclass(frozen=True)
class SpecialistBinding:
    specialist_type: CompetitorSpecialistType
    adapter_type: str
    adapter: A2ASpecialistAdapter


class A2ASpecialistRegistry:
    def __init__(self) -> None:
        self._bindings: dict[CompetitorSpecialistType, SpecialistBinding] = {}

    def bind(
        self,
        specialist_type: CompetitorSpecialistType,
        adapter: A2ASpecialistAdapter,
        *,
        replace: bool = False,
    ) -> None:
        if specialist_type in self._bindings and not replace:
            raise ValueError(f"adapter already bound for {specialist_type}")
        adapter_type = adapter.adapter_type.strip()
        if not adapter_type:
            raise ValueError("adapter_type cannot be empty")
        self._bindings[specialist_type] = SpecialistBinding(
            specialist_type=specialist_type,
            adapter_type=adapter_type,
            adapter=adapter,
        )

    def resolve(self, specialist_type: CompetitorSpecialistType) -> SpecialistBinding | None:
        return self._bindings.get(specialist_type)

    def bindings(self) -> tuple[SpecialistBinding, ...]:
        return tuple(self._bindings.values())

