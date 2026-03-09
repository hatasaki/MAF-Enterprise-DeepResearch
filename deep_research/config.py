"""Configuration loader for the Enterprise Deep Research workflow."""

from __future__ import annotations

import os
from dataclasses import dataclass, field  # noqa: F401 (field used by WorkflowConfig default_factory)


@dataclass
class KnowledgeBaseConfig:
    """Azure AI Search knowledge base configuration (Foundry IQ / agentic retrieval)."""

    endpoint: str
    api_key: str
    knowledge_base_name: str
    # Optional KQL filter for remote SharePoint knowledge source
    sharepoint_filter: str | None = None
    top_k: int = 10


@dataclass
class WorkflowConfig:
    """Magentic workflow tuning parameters."""

    max_rounds: int = 15
    max_stall: int = 3
    max_reset: int = 2
    enable_plan_review: bool = False
    intermediate_outputs: bool = True
    output_dir: str = "./outputs"


@dataclass
class AppConfig:
    """Top-level application configuration."""

    azure_project_endpoint: str
    azure_model_deployment: str
    knowledge_base: KnowledgeBaseConfig
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)


def load_config() -> AppConfig:
    """Load configuration from environment variables.

    Raises:
        EnvironmentError: When required variables are missing.
    """
    # ── Azure AI Foundry ──────────────────────────────────────────────────────
    endpoint = _require("AZURE_AI_PROJECT_ENDPOINT")
    deployment = _require("AZURE_AI_MODEL_DEPLOYMENT_NAME")

    # ── Azure AI Search (Knowledge Base / Foundry IQ) ─────────────────────────
    search_endpoint = _require("AZURE_SEARCH_ENDPOINT")
    search_api_key = _require("AZURE_SEARCH_API_KEY")
    knowledge_base_name = _require("AZURE_SEARCH_KNOWLEDGE_BASE_NAME")

    kb_cfg = KnowledgeBaseConfig(
        endpoint=search_endpoint,
        api_key=search_api_key,
        knowledge_base_name=knowledge_base_name,
        sharepoint_filter=os.getenv("AZURE_SEARCH_SHAREPOINT_FILTER"),
        top_k=int(os.getenv("AZURE_SEARCH_TOP_K", "10")),
    )

    # ── Workflow tuning ───────────────────────────────────────────────────────
    wf_cfg = WorkflowConfig(
        max_rounds=int(os.getenv("DEEP_RESEARCH_MAX_ROUNDS", "15")),
        max_stall=int(os.getenv("DEEP_RESEARCH_MAX_STALL", "3")),
        max_reset=int(os.getenv("DEEP_RESEARCH_MAX_RESET", "2")),
        enable_plan_review=os.getenv("DEEP_RESEARCH_PLAN_REVIEW", "false").lower() == "true",
        intermediate_outputs=os.getenv("DEEP_RESEARCH_INTERMEDIATE", "true").lower() == "true",
        output_dir=os.getenv("DEEP_RESEARCH_OUTPUT_DIR", "./outputs"),
    )

    return AppConfig(
        azure_project_endpoint=endpoint,
        azure_model_deployment=deployment,
        knowledge_base=kb_cfg,
        workflow=wf_cfg,
    )


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            "Copy .env.example to .env and fill in your values."
        )
    return value
