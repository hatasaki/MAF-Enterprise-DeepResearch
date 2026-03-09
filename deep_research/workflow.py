"""Enterprise Deep Research workflow built with Microsoft Agent Framework.

Architecture — Magentic pattern (MagenticBuilder):

    Manager (orchestrates, not a participant)
       │
       ├── ResearchAgent  — searches internal docs (Azure AI Search)
       ├── AnalystAgent   — critically synthesizes findings, identifies gaps
       └── ReportWriter   — composes the final structured report

The Manager uses MagenticBuilder's built-in progress-ledger logic to decide
who speaks next and when the task is complete.
"""

from __future__ import annotations

import logging
from typing import cast

from agent_framework import Agent, AgentResponseUpdate, Message
from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.orchestrations import (
    MagenticBuilder,
    MagenticPlanReviewRequest,
    MagenticPlanReviewResponse,
)
from azure.identity import AzureCliCredential, DefaultAzureCredential

from deep_research.config import AppConfig

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# System-prompt constants
# ─────────────────────────────────────────────────────────────────────────────

RESEARCHER_INSTRUCTIONS = """\
You are an expert enterprise research specialist with deep knowledge of information retrieval.

Your role is to search and retrieve relevant information from internal company documents
stored in SharePoint and other enterprise data sources via the Foundry IQ knowledge base.

When given a research task:
1. Decompose the query into specific, targeted search terms.
2. Use `search_internal_documents` to find relevant internal resources from the knowledge base.
3. Try multiple search queries from different angles to ensure thorough coverage.
4. Return comprehensive, well-organized findings with clear source citations.
5. Include the document title, source URL, and relevant excerpts for every finding.

Guidelines:
- Always explicitly cite your sources (document title + source URL).
- If a search returns no results, refine the query and try again with different keywords.
- Highlight any apparent information gaps or contradictions across sources.
- Do NOT fabricate information; rely only on retrieved content.
- The knowledge base enforces SharePoint document-level permissions automatically.
"""

ANALYST_INSTRUCTIONS = """\
You are a senior research analyst specializing in enterprise information synthesis.

Your role is to critically evaluate the gathered research findings and produce structured analysis.

When analyzing research findings:
1. Identify the most relevant and reliable information.
2. Assess completeness — flag any important aspects that are missing or unclear.
3. Cross-reference multiple sources to validate key claims.
4. Surface key insights, trends, and implications.
5. Note any conflicting information, outdated data, or low-confidence claims.

Your analysis must include:
- **Key Findings**: The most important facts and insights discovered.
- **Source Quality**: An assessment of source reliability (internal vs. web, recency).
- **Information Gaps**: Specific topics or data points that require further research.
- **Confidence Level**: Overall confidence in the collected evidence (High / Medium / Low).

Be specific and actionable. Do not write general statements — cite concrete evidence.
"""

WRITER_INSTRUCTIONS = """\
You are an expert technical writer specializing in enterprise research reports.

Your role is to synthesize all research and analysis into a professional, well-structured report.

Report structure (Markdown):
```
# [Report Title]

## Executive Summary
(2–3 sentences: what was researched, top finding, recommendation)

## Key Findings
(Bullet points or numbered list with evidence citations)

## Detailed Analysis
(Section per major topic; reference specific source documents)

## Recommendations
(Concrete, actionable recommendations based on the findings)

## Sources
(List every cited document: title, source path/URL, index)

## Limitations & Confidence
(What is uncertain, what data is missing, overall confidence level)
```

Guidelines:
- Every factual claim must be traceable to a cited source.
- Use precise language; avoid vague qualifiers.
- Format tables and code blocks where helpful.
- Keep the executive summary to ≤5 sentences.
- The report should be self-contained; include all context needed for a reader
  who has not seen the research conversation.
"""

MANAGER_INSTRUCTIONS = """\
You are an expert research manager coordinating a deep research team on enterprise topics.

Your team consists of:
- ResearchAgent: Searches internal documents via the Foundry IQ knowledge base (SharePoint and other sources).
- AnalystAgent: Critically evaluates findings and identifies gaps.
- ReportWriter: Composes the final structured research report.

Coordination strategy:
1. Start with ResearchAgent to gather initial information from internal documents.
2. Direct AnalystAgent to evaluate the gathered findings and identify gaps.
3. If gaps are identified, redirect ResearchAgent to fill them with targeted queries.
4. Repeat steps 2–3 until sufficient evidence has been collected (typically 2–3 cycles).
5. Engage ReportWriter to produce the final structured report.
6. Terminate when the report fully addresses the original research question.

Rules:
- Assign one agent at a time; give precise, focused instructions.
- Avoid redundant searches — if information was already retrieved, reuse it.
- Aim for depth over breadth; ensure the report is evidence-based.
- Terminate as soon as the report is complete and satisfactory.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Workflow builder
# ─────────────────────────────────────────────────────────────────────────────


def _create_client(cfg: AppConfig) -> AzureOpenAIResponsesClient:
    """Instantiate the Azure OpenAI Responses client."""
    try:
        credential = AzureCliCredential()
        # Verify the credential can be used (fast check)
        credential.get_token("https://management.azure.com/.default")
    except Exception:  # noqa: BLE001 — fall back to DefaultAzureCredential
        logger.info("AzureCliCredential unavailable; using DefaultAzureCredential.")
        credential = DefaultAzureCredential()  # type: ignore[assignment]

    return AzureOpenAIResponsesClient(
        project_endpoint=cfg.azure_project_endpoint,
        deployment_name=cfg.azure_model_deployment,
        credential=credential,
    )


def build_workflow(cfg: AppConfig, search_tools: list):
    """Build and return the Magentic deep-research workflow.

    Args:
        cfg: Application configuration (endpoints, tuning params).
        search_tools: List of ``@tool``-decorated callables for the ResearchAgent.

    Returns:
        A built workflow object ready to run via ``workflow.run(task, stream=True)``.
    """
    client = _create_client(cfg)

    # ── Participants ──────────────────────────────────────────────────────────
    researcher = client.as_agent(
        name="ResearchAgent",
        description="Searches enterprise internal documents and the web for information.",
        instructions=RESEARCHER_INSTRUCTIONS,
        tools=search_tools,
    )

    analyst = client.as_agent(
        name="AnalystAgent",
        description="Critically evaluates research findings and identifies information gaps.",
        instructions=ANALYST_INSTRUCTIONS,
    )

    writer = client.as_agent(
        name="ReportWriter",
        description="Composes structured, evidence-based research reports in Markdown.",
        instructions=WRITER_INSTRUCTIONS,
    )

    # ── Manager (orchestrator, not a participant) ─────────────────────────────
    manager = client.as_agent(
        name="ResearchManager",
        description="Orchestrates the research workflow and determines task completion.",
        instructions=MANAGER_INSTRUCTIONS,
    )

    # ── Magentic workflow ─────────────────────────────────────────────────────
    builder = MagenticBuilder(
        participants=[researcher, analyst, writer],
        manager_agent=manager,
        max_round_count=cfg.workflow.max_rounds,
        max_stall_count=cfg.workflow.max_stall,
        max_reset_count=cfg.workflow.max_reset,
        enable_plan_review=cfg.workflow.enable_plan_review,
        intermediate_outputs=cfg.workflow.intermediate_outputs,
    )

    return builder.build()


# ─────────────────────────────────────────────────────────────────────────────
# High-level runner
# ─────────────────────────────────────────────────────────────────────────────


async def run_deep_research(
    workflow,
    query: str,
    *,
    verbose: bool = True,
) -> str:
    """Execute the deep-research workflow for *query* and return the final report.

    The workflow may pause for human plan review if ``enable_plan_review=True``
    was set in the workflow configuration.

    Args:
        workflow: Built workflow from :func:`build_workflow`.
        query:    The research question to investigate.
        verbose:  Whether to stream intermediate agent outputs to stdout.

    Returns:
        The final research report as a Markdown string.
    """
    last_response_id: str | None = None
    final_report: str = ""

    async def _process_stream(stream) -> dict[str, MagenticPlanReviewResponse] | None:
        """Stream events, print intermediate output, and collect plan-review requests."""
        nonlocal last_response_id, final_report

        plan_requests: dict[str, MagenticPlanReviewRequest] = {}

        async for event in stream:
            # ── Human plan-review request ─────────────────────────────────────
            if event.type == "request_info" and event.request_type is MagenticPlanReviewRequest:
                plan_requests[event.request_id] = cast(MagenticPlanReviewRequest, event.data)

            # ── Streaming token from an agent ─────────────────────────────────
            elif event.type == "output" and isinstance(event.data, AgentResponseUpdate):
                if verbose and event.data.text:
                    rid = event.data.response_id
                    if rid != last_response_id:
                        if last_response_id is not None:
                            print()  # end previous agent's line
                        speaker = event.data.author_name or event.executor_id or "agent"
                        print(f"\n[{speaker}] ", end="", flush=True)
                        last_response_id = rid
                    print(event.data.text, end="", flush=True)

            # ── Final output (list[Message]) ──────────────────────────────────
            elif event.type == "output" and isinstance(event.data, list):
                messages: list[Message] = cast(list[Message], event.data)
                # The last assistant message from ReportWriter is our final report
                for msg in reversed(messages):
                    if msg.role == "assistant" and msg.text:
                        # Prefer the ReportWriter's message
                        if msg.author_name == "ReportWriter" or "##" in (msg.text or ""):
                            final_report = msg.text or ""
                            break
                # Fall back to last assistant message if ReportWriter not found
                if not final_report:
                    for msg in reversed(messages):
                        if msg.role == "assistant" and msg.text:
                            final_report = msg.text or ""
                            break

        # ── Handle plan-review requests (interactive) ─────────────────────────
        if not plan_requests:
            return None

        responses: dict[str, MagenticPlanReviewResponse] = {}
        for req_id, req in plan_requests.items():
            if verbose:
                print("\n\n" + "=" * 60)
                print("PLAN REVIEW REQUEST")
                print("=" * 60)
                if req.current_progress is not None:
                    print(f"Current progress:\n{req.current_progress}\n")
                print(f"Proposed plan:\n{req.plan.text}\n")
                print("Press <Enter> to approve, or type feedback to revise:")
            user_input = input("> ").strip()  # noqa: ASYNC250
            if user_input:
                if verbose:
                    print("Plan revised.\n")
                responses[req_id] = req.revise(user_input)
            else:
                if verbose:
                    print("Plan approved.\n")
                responses[req_id] = req.approve()

        return responses

    # ── Run workflow (with optional plan-review loop) ─────────────────────────
    if verbose:
        print("=" * 70)
        print(f"Deep Research Query: {query}")
        print("=" * 70)

    stream = workflow.run(query, stream=True)
    pending = await _process_stream(stream)

    while pending is not None:
        stream = workflow.run(stream=True, responses=pending)
        pending = await _process_stream(stream)

    if verbose:
        print("\n\n" + "=" * 70)
        print("Research complete.")
        print("=" * 70)

    return final_report or "Research completed but no report was generated."
