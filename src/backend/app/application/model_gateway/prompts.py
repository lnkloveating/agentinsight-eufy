"""不依赖模型 SDK 的版本化 Prompt Registry。"""

from dataclasses import dataclass
from string import Formatter
from typing import Any


class PromptRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class PromptDefinition:
    prompt_key: str
    version: str
    system_template: str
    user_template: str

    def __post_init__(self) -> None:
        if not self.prompt_key.strip() or not self.version.strip():
            raise PromptRegistryError("prompt key and version cannot be empty")
        self._variables(self.system_template)
        self._variables(self.user_template)

    def render(self, variables: dict[str, Any]) -> "RenderedPrompt":
        required = self._variables(self.system_template) | self._variables(
            self.user_template
        )
        missing = sorted(required - set(variables))
        if missing:
            raise PromptRegistryError(f"missing prompt variables: {', '.join(missing)}")
        values = {key: str(value) for key, value in variables.items()}
        return RenderedPrompt(
            system=self.system_template.format_map(values),
            user=self.user_template.format_map(values),
        )

    @staticmethod
    def _variables(template: str) -> set[str]:
        result: set[str] = set()
        for _, field_name, format_spec, conversion in Formatter().parse(template):
            if field_name is None:
                continue
            if not field_name.isidentifier() or format_spec or conversion:
                raise PromptRegistryError(
                    "prompt variables must be simple identifiers without formatting"
                )
            result.add(field_name)
        return result


@dataclass(frozen=True)
class RenderedPrompt:
    system: str
    user: str


class PromptRegistry:
    def __init__(self) -> None:
        self._definitions: dict[tuple[str, str], PromptDefinition] = {}
        self._active_versions: dict[str, str] = {}

    def register(
        self,
        definition: PromptDefinition,
        *,
        activate: bool = False,
        replace: bool = False,
    ) -> None:
        key = (definition.prompt_key, definition.version)
        if key in self._definitions and not replace:
            raise PromptRegistryError(f"prompt already registered: {key}")
        self._definitions[key] = definition
        if activate or definition.prompt_key not in self._active_versions:
            self._active_versions[definition.prompt_key] = definition.version

    def resolve(
        self, prompt_key: str, version: str | None = None
    ) -> PromptDefinition:
        resolved_version = version or self._active_versions.get(prompt_key)
        if resolved_version is None:
            raise PromptRegistryError(f"prompt is not registered: {prompt_key}")
        definition = self._definitions.get((prompt_key, resolved_version))
        if definition is None:
            raise PromptRegistryError(
                f"prompt version is not registered: {prompt_key}:{resolved_version}"
            )
        return definition

    def activate(self, prompt_key: str, version: str) -> None:
        if (prompt_key, version) not in self._definitions:
            raise PromptRegistryError(
                f"prompt version is not registered: {prompt_key}:{version}"
            )
        self._active_versions[prompt_key] = version
