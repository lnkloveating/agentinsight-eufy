"""确定性的多 Provider 模型目录。"""

import json

from pydantic import TypeAdapter, ValidationError

from app.application.model_gateway.contracts import CredentialResolver, ModelDefinition
from app.schemas.model import ModelPage, ModelSummary


class ModelCatalogError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ModelCatalog:
    def __init__(
        self,
        definitions: list[ModelDefinition],
        *,
        default_model_id: str | None = None,
    ) -> None:
        self._definitions: dict[str, ModelDefinition] = {}
        for definition in definitions:
            if definition.model_id in self._definitions:
                raise ModelCatalogError(
                    "MODEL_ID_DUPLICATED",
                    f"duplicate model id: {definition.model_id}",
                )
            self._definitions[definition.model_id] = definition
        normalized_default = default_model_id.strip().lower() if default_model_id else None
        if normalized_default is not None and normalized_default not in self._definitions:
            raise ModelCatalogError(
                "DEFAULT_MODEL_NOT_FOUND",
                f"default model is not configured: {normalized_default}",
            )
        self.default_model_id = normalized_default

    @classmethod
    def from_json(
        cls,
        raw_catalog: str,
        *,
        default_model_id: str | None = None,
    ) -> "ModelCatalog":
        try:
            payload = json.loads(raw_catalog or "[]")
            definitions = TypeAdapter(list[ModelDefinition]).validate_python(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ModelCatalogError(
                "MODEL_CATALOG_INVALID", "MODEL_CATALOG_JSON is invalid"
            ) from exc
        return cls(definitions, default_model_id=default_model_id)

    def get(self, model_id: str) -> ModelDefinition | None:
        return self._definitions.get(model_id.strip().lower())

    def require_enabled(self, model_id: str) -> ModelDefinition:
        definition = self.get(model_id)
        if definition is None:
            raise ModelCatalogError("MODEL_NOT_FOUND", "requested model is not configured")
        if not definition.enabled:
            raise ModelCatalogError("MODEL_DISABLED", "requested model is disabled")
        return definition

    def public_page(self, credentials: CredentialResolver) -> ModelPage:
        enabled = sorted(
            (definition for definition in self._definitions.values() if definition.enabled),
            key=lambda item: (item.provider, item.display_name, item.model_id),
        )
        items = [
            ModelSummary(
                model_id=item.model_id,
                provider=item.provider,
                display_name=item.display_name,
                capabilities=item.capabilities,
                enabled=item.enabled,
                credential_available=credentials.available(item.credential_env),
                context_window=item.context_window,
                input_cost_microusd_per_million_tokens=(
                    item.input_cost_microusd_per_million_tokens
                ),
                output_cost_microusd_per_million_tokens=(
                    item.output_cost_microusd_per_million_tokens
                ),
            )
            for item in enabled
        ]
        available_ids = {item.model_id for item in items if item.credential_available}
        default_model_id = (
            self.default_model_id if self.default_model_id in available_ids else None
        )
        return ModelPage(items=items, default_model_id=default_model_id)

    def definitions(self) -> tuple[ModelDefinition, ...]:
        return tuple(self._definitions.values())
