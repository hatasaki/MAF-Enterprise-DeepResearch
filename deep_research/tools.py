"""Search tools for enterprise internal documents using Azure AI Search Knowledge Base.

Uses ``KnowledgeBaseRetrievalClient`` (agentic retrieval) to query a knowledge
base that includes a remote SharePoint knowledge source.  The user's identity
token is forwarded via the ``x-ms-query-source-authorization`` header so that
SharePoint document-level permissions are enforced at query time.

The ``@tool`` decorator from Microsoft Agent Framework exposes the retrieval
function as a callable tool for agents.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated

from agent_framework import tool
from azure.core.credentials import AzureKeyCredential
from azure.identity import AzureCliCredential, DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient
from azure.search.documents.knowledgebases.models import (
    KnowledgeBaseMessage,
    KnowledgeBaseMessageTextContent,
    KnowledgeBaseRetrievalRequest,
    RemoteSharePointKnowledgeSourceParams,
)

from deep_research.config import KnowledgeBaseConfig

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Token helper
# ─────────────────────────────────────────────────────────────────────────────


def _get_user_token_provider():
    """Return a callable that provides a fresh bearer token for SharePoint."""
    try:
        credential = AzureCliCredential()
        credential.get_token("https://search.azure.com/.default")
    except Exception:  # noqa: BLE001
        logger.info("AzureCliCredential unavailable; using DefaultAzureCredential for SharePoint token.")
        credential = DefaultAzureCredential()  # type: ignore[assignment]
    return get_bearer_token_provider(credential, "https://search.azure.com/.default")


# ─────────────────────────────────────────────────────────────────────────────
# Internal document search via Knowledge Base (agentic retrieval)
# ─────────────────────────────────────────────────────────────────────────────


def _build_knowledge_base_search_tool(cfg: KnowledgeBaseConfig):
    """Return a ``@tool``-decorated async function that queries a knowledge base."""

    kb_client = KnowledgeBaseRetrievalClient(
        endpoint=cfg.endpoint,
        knowledge_base_name=cfg.knowledge_base_name,
        credential=AzureKeyCredential(cfg.api_key),
    )

    token_provider = _get_user_token_provider()

    @tool(description=(
        "Search enterprise internal documents via the Foundry IQ knowledge base. "
        "This tool queries SharePoint and other knowledge sources connected to the "
        "knowledge base, returning synthesized answers with source citations. "
        "Use this tool to find information from the company's internal documents."
    ))
    async def search_internal_documents(
        query: Annotated[str, "The search query to look up in internal documents"],
    ) -> str:
        """Query the knowledge base and return a formatted response."""
        try:
            # Build messages for the retrieval request
            messages = [
                KnowledgeBaseMessage(
                    role="user",
                    content=[KnowledgeBaseMessageTextContent(text=query)],
                ),
            ]

            # Build knowledge source params for remote SharePoint
            knowledge_source_params = None
            if cfg.sharepoint_filter:
                knowledge_source_params = [
                    RemoteSharePointKnowledgeSourceParams(
                        knowledge_source_name=None,  # applies to all remote SP sources
                        filter_expression_add_on=cfg.sharepoint_filter,
                        include_references=True,
                        include_reference_source_data=True,
                    ),
                ]

            request = KnowledgeBaseRetrievalRequest(
                messages=messages,
                knowledge_source_params=knowledge_source_params,
                include_activity=True,
            )

            # Get a fresh access token for SharePoint authorization
            user_token = token_provider()

            # Call retrieve with the user token for SharePoint ACL enforcement
            result = kb_client.retrieve(
                retrieval_request=request,
                x_ms_query_source_authorization=user_token,
            )

            # Format the response
            lines: list[str] = []

            # Extract the main response text
            if result.response:
                for msg in result.response:
                    if msg.content:
                        for content_item in msg.content:
                            text = getattr(content_item, "text", None)
                            if text:
                                # The text may be JSON-serialized array of results
                                try:
                                    parsed = json.loads(text)
                                    if isinstance(parsed, list):
                                        lines.append(f"Found {len(parsed)} result(s) from knowledge base:\n")
                                        for i, item in enumerate(parsed, start=1):
                                            lines.append(f"--- Result {i} ---")
                                            if item.get("title"):
                                                lines.append(f"Title: {item['title']}")
                                            if item.get("webUrl"):
                                                lines.append(f"Source: {item['webUrl']}")
                                            if item.get("content"):
                                                content_text = item["content"][:2000]
                                                lines.append(f"Content:\n{content_text}\n")
                                            elif item.get("terms"):
                                                lines.append(f"Terms: {item['terms']}\n")
                                    elif isinstance(parsed, str):
                                        lines.append(parsed)
                                    else:
                                        lines.append(text)
                                except (json.JSONDecodeError, TypeError):
                                    # Plain text response (e.g. answer synthesis)
                                    lines.append(text)

            # Extract references if available
            if result.references:
                lines.append("\n--- References ---")
                for ref in result.references:
                    ref_id = getattr(ref, "id", "")
                    doc_key = getattr(ref, "doc_key", "")
                    web_url = getattr(ref, "web_url", "")
                    source_data = getattr(ref, "source_data", None)
                    ref_info = f"[{ref_id}]"
                    if doc_key:
                        ref_info += f" {doc_key}"
                    if web_url:
                        ref_info += f" ({web_url})"
                    lines.append(ref_info)

                    if source_data and isinstance(source_data, dict):
                        for key, value in source_data.items():
                            if value and key not in ("id",):
                                lines.append(f"  {key}: {value}")

            if not lines:
                return "No relevant documents found in the knowledge base."

            return "\n".join(lines)

        except Exception as exc:  # noqa: BLE001
            logger.warning("Knowledge base retrieval failed: %s", exc)
            return f"Knowledge base retrieval failed: {exc}"

    return search_internal_documents


# ─────────────────────────────────────────────────────────────────────────────
# Public factory
# ─────────────────────────────────────────────────────────────────────────────


def build_search_tools(kb_cfg: KnowledgeBaseConfig) -> list:
    """Build search tools for the ResearchAgent.

    Returns a list containing the ``@tool``-decorated knowledge base retrieval
    callable, ready to be passed to an ``Agent`` constructor.
    """
    return [_build_knowledge_base_search_tool(kb_cfg)]
