# Enterprise Deep Research Agent

> **Microsoft Agent Framework** — Deep Research agent workflow for enterprise internal use

---

## Overview

This system automatically generates high-quality research reports targeting internal documents using **Foundry IQ** (Azure AI Search knowledge base) and a **remote SharePoint Knowledge Source**.

It uses **MagenticBuilder** (the orchestration capability of Microsoft Agent Framework) to deliver a streamlined workflow with a minimal configuration of 3 agents + 1 manager.

---

## Architecture

```
query
  │
  ▼
┌──────────────────────────────────────────────────────────┐
│           MagenticBuilder (Orchestrator)                  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │          ResearchManager (manager agent)             │  │
│  │   - Progress evaluation & next agent selection       │  │
│  │   - Task completion determination                    │  │
│  └──────────────┬──────────────────────────────────────┘  │
│                 │ Instructions (controlled by MagenticBuilder) │
│    ┌────────────┼────────────┐                            │
│    ▼            ▼            ▼                            │
│ ResearchAgent AnalystAgent ReportWriter                   │
│ (Participant 1) (Participant 2) (Participant 3)           │
└──────────────────────────────────────────────────────────┘
  │                │               │
  ▼                ▼               ▼
Foundry IQ       Analysis &    Markdown Report
Knowledge Base   Integration   Structured with
 (remote SP)     Gap Analysis  Citations
```

### Agent Roles

| Agent | Role | Tools |
|---|---|---|
| **ResearchAgent** | Search and collect information from internal documents such as SharePoint | `search_internal_documents` |
| **AnalystAgent** | Critical evaluation, gap analysis, and synthesis of information | None (LLM analysis) |
| **ReportWriter** | Write the final report (Markdown format with citations) | None (LLM generation) |
| **ResearchManager** | Workflow coordination and completion determination (Magentic manager) | None |

### Search Architecture

This implementation uses a **remote SharePoint Knowledge Source** via the **Azure AI Search knowledge base (Foundry IQ)**. By adding additional indexes to the same knowledge source, Foundry IQ's Agentic Retrieval can also retrieve that information.

---

## Setup

### 1. Prerequisites

- Python 3.11 or higher
- Microsoft Foundry (Agent Service v2 / Responses API)
- Azure AI Search (Standard S1 or higher recommended — for enabling semantic search)
  - A Knowledge Base must already be created
  - A remote SharePoint Knowledge Source must be connected to the knowledge base
- SharePoint Online (same Microsoft Entra ID tenant as Azure)
- Copilot license (required for using remote SharePoint)
- [az CLI](https://docs.microsoft.com/en-us/cli/azure/) (default authentication via `az login`)

### 1.5. Creating Knowledge Sources and Knowledge Bases

To use this system, you must first create a **remote SharePoint Knowledge Source** and a **Knowledge Base** on Azure AI Search.

#### (1) Creating a remote SharePoint Knowledge Source

You can create one via the Azure portal, Python SDK, or REST API. The following is an example using the Python SDK:

```python
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    RemoteSharePointKnowledgeSource,
    RemoteSharePointKnowledgeSourceParameters,
)

index_client = SearchIndexClient(
    endpoint="https://<your-search-service>.search.windows.net",
    credential=AzureKeyCredential("<your-api-key>"),
)

knowledge_source = RemoteSharePointKnowledgeSource(
    name="my-remote-sharepoint-ks",
    description="Knowledge source for internal SharePoint documents",
    remote_share_point_parameters=RemoteSharePointKnowledgeSourceParameters(
        # KQL filter (optional): restrict to specific file types or sites
        filter_expression='FileExtension:"docx" OR FileExtension:"pdf"',
        # Metadata fields to return (optional)
        resource_metadata=["Author", "Title"],
    ),
)

index_client.create_or_update_knowledge_source(knowledge_source)
print(f"Knowledge source '{knowledge_source.name}' created.")
```

To add an existing index to a knowledge source, add the following:

```python
from azure.search.documents.indexes.models import (
    SearchIndexKnowledgeSource,
    KnowledgeSourceReference,
)

# Create an existing index as a knowledge source
index_ks = SearchIndexKnowledgeSource(
    name="my-index-ks",
    description="Existing search index",
    index_name="my-existing-index",
)
index_client.create_or_update_knowledge_source(index_ks)

# Associate both sources with the knowledge base
knowledge_base.knowledge_sources = [
    KnowledgeSourceReference(name="my-remote-sharepoint-ks"),
    KnowledgeSourceReference(name="my-index-ks"),
]
index_client.create_or_update_knowledge_base(knowledge_base)
```

**Filter expression examples:**

| Purpose | Filter Expression |
|---|---|
| Restrict to a specific site | `Path:"https://contoso.sharepoint.com/sites/hr/Shared Documents"` |
| Specify by site ID | `SiteID:"00aa00aa-bb11-cc22-dd33-44ee44ee44ee"` |
| File type | `FileExtension:"docx" OR FileExtension:"pdf" OR FileExtension:"pptx"` |
| Date range | `LastModifiedTime >= 2024-01-01 AND LastModifiedTime <= 2025-12-31` |

#### (2) Creating a Knowledge Base

Associate the created knowledge source with a knowledge base:

```python
from azure.search.documents.indexes.models import (
    KnowledgeBase,
    KnowledgeBaseAzureOpenAIModel,
    KnowledgeRetrievalLowReasoningEffort,
    KnowledgeRetrievalOutputMode,
    KnowledgeSourceReference,
    AzureOpenAIVectorizerParameters,
)

aoai_params = AzureOpenAIVectorizerParameters(
    resource_url="https://<your-aoai>.openai.azure.com",
    deployment_name="gpt-4o",
    model_name="gpt-4o",
)

knowledge_base = KnowledgeBase(
    name="my-enterprise-kb",
    knowledge_sources=[
        KnowledgeSourceReference(name="my-remote-sharepoint-ks"),
    ],
    models=[KnowledgeBaseAzureOpenAIModel(azure_open_ai_parameters=aoai_params)],
    output_mode=KnowledgeRetrievalOutputMode.ANSWER_SYNTHESIS,
    retrieval_reasoning_effort=KnowledgeRetrievalLowReasoningEffort(),
)

index_client.create_or_update_knowledge_base(knowledge_base)
print(f"Knowledge base '{knowledge_base.name}' created.")
```

> **Note**: Set the knowledge base name in `AZURE_SEARCH_KNOWLEDGE_BASE_NAME` in your `.env` file.

For more details, refer to the official documentation:
- [Create a remote SharePoint Knowledge Source](https://learn.microsoft.com/azure/search/agentic-knowledge-source-how-to-sharepoint-remote)
- [Create a Knowledge Base](https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-create-knowledge-base)

### 2. Installation

```bash
# Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/macOS

# Install dependencies (--pre flag required)
pip install -r requirements.txt --pre
```

### 3. Configure Environment Variables

```bash
cp .env.example .env
```

Edit the `.env` file and configure the following required fields:

| Variable | Description |
|---|---|
| `AZURE_AI_PROJECT_ENDPOINT` | Azure AI Foundry Agent Service v2 project endpoint |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Model deployment name (e.g., GPT-4o) |
| `AZURE_SEARCH_ENDPOINT` | Azure AI Search service endpoint |
| `AZURE_SEARCH_API_KEY` | Azure AI Search API key |
| `AZURE_SEARCH_KNOWLEDGE_BASE_NAME` | Knowledge base name |

Optional settings:

```env
# KQL filter for SharePoint search (narrow down by specific site or file type)
AZURE_SEARCH_SHAREPOINT_FILTER=FileExtension:"docx" OR FileExtension:"pdf"

# Maximum number of results (default: 10)
AZURE_SEARCH_TOP_K=10

# Maximum number of rounds (default: 15)
DEEP_RESEARCH_MAX_ROUNDS=15
```

### 4. Authentication

```bash
# Log in with Azure CLI
az login
```

---

## Usage

### Basic Usage

```bash
python main.py --query "Summarize the cloud migration plan for 2025"
```

### Advanced Options

```bash
# Specify an output file
python main.py --query "..." --output ./my_report.md

# Enable plan review (review/modify the research plan before execution)
python main.py --query "..." --plan-review

# Hide intermediate output and show only the final report
python main.py --query "..." --no-stream

# Enable debug logging
python main.py --query "..." --verbose
```

### Output

- A Markdown report is saved to `./outputs/research_<query>_<timestamp>.md`
- The report includes:
  - Executive summary
  - Key findings (with source citations)
  - Detailed analysis
  - Recommendations
  - Source list
  - Confidence level and limitations

---

## Project Structure

```
maf-enterprise-deepresearch/
├── main.py                    # CLI entry point
├── requirements.txt           # Dependencies
├── .env.example               # Environment variable template
├── README.md                  # This file
└── deep_research/
    ├── __init__.py            # Package public API
    ├── config.py              # Configuration loader
    ├── tools.py               # Search tools (Azure AI Search)
    └── workflow.py            # Magentic workflow definition
```

---

## Technologies Used

| Component | Package / Service |
|---|---|
| LLM Orchestration | `agent-framework` (Microsoft Agent Framework 1.0.0rc3) |
| Magentic Pattern | `agent-framework-orchestrations` |
| Azure OpenAI Connection | `AzureOpenAIResponsesClient` (Agent Service v2 / Responses API) |
| Internal Document Search | `azure-search-documents` (Foundry IQ Knowledge Base + remote SharePoint) |
| Authentication | `azure-identity` (AzureCliCredential / DefaultAzureCredential) |

---

## References

- [Microsoft Agent Framework GitHub](https://github.com/microsoft/agent-framework)
- [Microsoft Agent Framework Documentation](https://learn.microsoft.com/en-us/agent-framework/)
- [Magentic Orchestration Samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/03-workflows/orchestrations)
- [Reference Repository: kushanon/Deep-Research-Agents](https://github.com/kushanon/Deep-Research-Agents)
