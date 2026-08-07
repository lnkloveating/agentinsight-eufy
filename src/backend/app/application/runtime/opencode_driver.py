from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import cast
from urllib.parse import urlsplit

from app.application.runtime.cli_contracts import CliCommand, CliWorkspace
from app.application.runtime.contracts import AgentInvocation
from app.schemas.runtime import RuntimeCapability

_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,119}$")


class ExternalCliOutputError(ValueError):
    pass


@dataclass(frozen=True)
class OpenCodeCliDriver:
    executable: str
    provider_id: str
    provider_name: str
    provider_base_url: str
    provider_model: str
    credential_env: str
    enabled: bool = True

    runtime_id = "opencode"
    display_name = "OpenCode"
    adapter_type = "external_cli"
    capabilities = (
        RuntimeCapability.TEXT,
        RuntimeCapability.STRUCTURED_OUTPUT,
        RuntimeCapability.LOCAL_FILES,
    )

    def __post_init__(self) -> None:
        if not _ENV_NAME.fullmatch(self.credential_env):
            raise ValueError("credential_env must be an uppercase environment variable name")
        if not self.provider_id.strip() or not self.provider_model.strip():
            raise ValueError("OpenCode provider and model cannot be blank")
        parsed_url = urlsplit(self.provider_base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("OpenCode provider base URL must be HTTP(S)")

    @property
    def model_id(self) -> str:
        return f"{self.provider_id}/{self.provider_model}"

    def version_arguments(self) -> tuple[str, ...]:
        return ("--version",)

    def prepare(
        self,
        invocation: AgentInvocation,
        workspace: CliWorkspace,
        credential: str,
    ) -> CliCommand:
        del invocation
        config_path = workspace.state_dir / "opencode.json"
        config = {
            "$schema": "https://opencode.ai/config.json",
            "model": self.model_id,
            "permission": {
                "*": "deny",
                "read": "allow",
                "glob": "allow",
                "grep": "allow",
                "list": "allow",
                "edit": "deny",
                "bash": "deny",
                "task": "deny",
                "external_directory": "deny",
                "webfetch": "deny",
                "websearch": "deny",
                "question": "deny",
            },
            "provider": {
                self.provider_id: {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": self.provider_name,
                    "options": {
                        "baseURL": self.provider_base_url,
                        "apiKey": f"{{env:{self.credential_env}}}",
                    },
                    "models": {
                        self.provider_model: {"name": self.provider_model},
                    },
                }
            },
        }
        config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        instruction = (
            "Read input/invocation.json. Complete only the requested research task. "
            "Return one JSON object matching the ResearchArtifact fields in that file's "
            "task contract. Do not use markdown fences or add explanatory text."
        )
        environment = {
            self.credential_env: credential,
            "OPENCODE_CONFIG": str(config_path),
            "OPENCODE_CONFIG_DIR": str(workspace.state_dir),
            "OPENCODE_DISABLE_AUTOUPDATE": "true",
            "OPENCODE_DISABLE_DEFAULT_PLUGINS": "true",
            "OPENCODE_DISABLE_CLAUDE_CODE": "true",
            "OPENCODE_DISABLE_LSP_DOWNLOAD": "true",
            "OPENCODE_CLIENT": "agentinsight",
        }
        return CliCommand(
            executable=self.executable,
            arguments=(
                "--pure",
                "run",
                "--format",
                "json",
                "--model",
                self.model_id,
                "--dir",
                str(workspace.root),
                instruction,
            ),
            environment=environment,
        )

    def decode_output(self, stdout: bytes) -> object:
        text = stdout.decode("utf-8", errors="strict").strip()
        if not text:
            raise ExternalCliOutputError("OpenCode returned empty output")

        direct = self._try_json(text)
        if self._looks_like_artifact(direct):
            return direct

        completed_texts: list[str] = []
        for line in text.splitlines():
            event = self._try_json(line.strip())
            if not isinstance(event, dict):
                continue
            part = event.get("part")
            if not isinstance(part, dict):
                properties = event.get("properties")
                if isinstance(properties, dict):
                    part = properties.get("part")
            event_type = event.get("type")
            if isinstance(part, dict) and part.get("type") == "text":
                part_text = part.get("text")
                if isinstance(part_text, str) and part_text.strip():
                    completed_texts.append(part_text)
            elif event_type == "text" and isinstance(event.get("text"), str):
                completed_texts.append(str(event["text"]))

        for candidate in reversed(completed_texts):
            parsed = self._extract_json_object(candidate)
            if self._looks_like_artifact(parsed):
                return parsed
        raise ExternalCliOutputError("OpenCode output did not contain a ResearchArtifact")

    @staticmethod
    def _try_json(value: str) -> object | None:
        try:
            return cast(object, json.loads(value))
        except json.JSONDecodeError:
            return None

    @classmethod
    def _extract_json_object(cls, value: str) -> object | None:
        stripped = value.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            lines = stripped.splitlines()
            stripped = "\n".join(lines[1:-1]).strip()
        direct = cls._try_json(stripped)
        if direct is not None:
            return direct
        decoder = json.JSONDecoder()
        for index, character in enumerate(stripped):
            if character != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(stripped[index:])
            except json.JSONDecodeError:
                continue
            return cast(object, parsed)
        return None

    @staticmethod
    def _looks_like_artifact(value: object | None) -> bool:
        if not isinstance(value, dict):
            return False
        required = {
            "artifact_id",
            "task_id",
            "artifact_type",
            "status",
            "payload",
            "evidence_ids",
            "contradictions",
            "unknowns",
            "quality_score",
            "errors",
        }
        return required.issubset(value)
