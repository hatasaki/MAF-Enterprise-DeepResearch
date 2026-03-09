"""Validation test for the deep_research package (no real Azure credentials needed)."""

import os
import sys

sys.path.insert(0, ".")

# Mock env before imports
os.environ.update({
    "AZURE_AI_PROJECT_ENDPOINT": "https://test.services.ai.azure.com/api/projects/test",
    "AZURE_AI_MODEL_DEPLOYMENT_NAME": "gpt-4o",
    "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
    "AZURE_SEARCH_API_KEY": "test-key",
    "AZURE_SEARCH_KNOWLEDGE_BASE_NAME": "test-knowledge-base",
})

from unittest.mock import MagicMock, patch  # noqa: E402

from deep_research.config import load_config  # noqa: E402
from deep_research.tools import build_search_tools  # noqa: E402
from deep_research.workflow import (  # noqa: E402
    ANALYST_INSTRUCTIONS,
    MANAGER_INSTRUCTIONS,
    RESEARCHER_INSTRUCTIONS,
    WRITER_INSTRUCTIONS,
    build_workflow,
)

# ── Config ────────────────────────────────────────────────────────────────────
cfg = load_config()
assert cfg.azure_project_endpoint == "https://test.services.ai.azure.com/api/projects/test"
assert cfg.knowledge_base.knowledge_base_name == "test-knowledge-base"
assert cfg.knowledge_base.endpoint == "https://test.search.windows.net"
print("config OK")

# ── Tools ─────────────────────────────────────────────────────────────────────
mock_token_provider = MagicMock(return_value="mock-token")
with (
    patch("deep_research.tools._get_user_token_provider", return_value=mock_token_provider),
    patch("deep_research.tools.KnowledgeBaseRetrievalClient"),
):
    tools = build_search_tools(cfg.knowledge_base)
assert len(tools) == 1
assert tools[0].name == "search_internal_documents"
print(f"tools OK: {[t.name for t in tools]}")

# ── Agent instructions ────────────────────────────────────────────────────────
for name, inst in [
    ("MANAGER", MANAGER_INSTRUCTIONS),
    ("RESEARCHER", RESEARCHER_INSTRUCTIONS),
    ("ANALYST", ANALYST_INSTRUCTIONS),
    ("WRITER", WRITER_INSTRUCTIONS),
]:
    assert len(inst) > 100, f"{name} instructions appear empty"
print("system prompts OK")

# ── Workflow construction ─────────────────────────────────────────────────────
mock_cred = MagicMock()
mock_client = MagicMock()
mock_client.as_agent.return_value = MagicMock()
mock_workflow = MagicMock()

with (
    patch("deep_research.workflow.AzureCliCredential", return_value=mock_cred),
    patch("deep_research.workflow.DefaultAzureCredential", return_value=mock_cred),
    patch("deep_research.workflow.AzureOpenAIResponsesClient", return_value=mock_client),
    patch("deep_research.workflow.MagenticBuilder") as MockBuilder,
):
    MockBuilder.return_value.build.return_value = mock_workflow
    _ = build_workflow(cfg, tools)
    kw = MockBuilder.call_args.kwargs

assert kw["participants"] is not None and len(kw["participants"]) == 3, (
    f"Expected 3 participants, got {len(kw['participants'])}"
)
assert kw["manager_agent"] is not None, "manager_agent must be set"
assert kw["max_round_count"] == 15
assert kw["max_stall_count"] == 3
assert kw["max_reset_count"] == 2
print(f"workflow construction OK: {len(kw['participants'])} participants, manager_agent set")

print()
print("All validation checks passed!")
