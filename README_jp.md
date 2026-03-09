# Enterprise Deep Research Agent

> **Microsoft Agent Framework**  による企業内部向けDeep Researchエージェントワークフロー

---

## 概要

**Foundry IQ** (Azure AI Search のナレッジベース) と **remote SharePoint Knowledge Source** を利用して、社内ドキュメントを対象にした高品質なリサーチレポートを自動生成するシステムです。

**MagenticBuilder** (Microsoft Agent Framework のオーケストレーション機能) を使用し、最小構成の3エージェント＋1マネージャーで合理的なワークフローを実現しています。

---

## アーキテクチャ

```
query
  │
  ▼
┌──────────────────────────────────────────────────────────┐
│           MagenticBuilder (Orchestrator)                  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │          ResearchManager (manager agent)             │  │
│  │   - 進捗評価・次のエージェント決定                      │  │
│  │   - タスク完了判断                                     │  │
│  └──────────────┬──────────────────────────────────────┘  │
│                 │ 指示 (MagenticBuilder が制御)             │
│    ┌────────────┼────────────┐                            │
│    ▼            ▼            ▼                            │
│ ResearchAgent AnalystAgent ReportWriter                   │
│ (参加者1)     (参加者2)     (参加者3)                       │
└──────────────────────────────────────────────────────────┘
  │                │               │
  ▼                ▼               ▼
Foundry IQ       分析・統合  Markdownレポート
Knowledge Base   情報ギャップ特定  引用付き構造化
 (remote SP)
```

### エージェントの役割

| エージェント | 役割 | ツール |
|---|---|---|
| **ResearchAgent** | SharePoint 等の社内ドキュメント検索・情報収集 | `search_internal_documents` |
| **AnalystAgent** | 情報の批判的評価・ギャップ分析・統合 | なし(LLM分析) |
| **ReportWriter** | 最終レポート執筆(Markdown形式、引用付き) | なし(LLM生成) |
| **ResearchManager** | ワークフロー調整・完了判断(Magenticマネージャー) | なし |

### 検索アーキテクチャ

本実装では **Azure AI Search のナレッジベース (Foundry IQ)** 経由で **remote SharePoint Knowledge Source** を利用しています。同じナレッジソースにインデックスを追加すれば、Foundry IQ の Agentic Retrieval でその情報も取得可能です。

---

## セットアップ

### 1. 前提条件

- Python 3.11 以上
- Microsoft Foundry (Agent Service v2 / Responses API)
- Azure AI Search (Standard S1 以上を推奨 ー セマンティック検索有効化のため)
  - ナレッジベース (Knowledge Base) が作成済みであること
  - remote SharePoint Knowledge Source がナレッジベースに接続済みであること
- SharePoint Online (Azure と同一の Microsoft Entra ID テナント)
- Copilot ライセンス (remote SharePoint の利用に必要)
- [az CLI](https://docs.microsoft.com/en-us/cli/azure/) (`az login` によるデフォルト認証)

### 1.5. ナレッジソースとナレッジベースの作成

本システムを利用するには、Azure AI Search 上に **remote SharePoint Knowledge Source** と **ナレッジベース (Knowledge Base)** を事前に作成する必要があります。

#### (1) remote SharePoint Knowledge Source の作成

Azure portal、Python SDK、または REST API で作成できます。以下は Python SDK の例です：

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
    description="社内 SharePoint ドキュメントのナレッジソース",
    remote_share_point_parameters=RemoteSharePointKnowledgeSourceParameters(
        # KQL フィルタ (任意): 特定のファイルタイプやサイトに限定
        filter_expression='FileExtension:"docx" OR FileExtension:"pdf"',
        # 返却するメタデータフィールド (任意)
        resource_metadata=["Author", "Title"],
    ),
)

index_client.create_or_update_knowledge_source(knowledge_source)
print(f"Knowledge source '{knowledge_source.name}' created.")
```

既存インデックスをナレッジソースに追加する場合は下記を追加してください：

```python
from azure.search.documents.indexes.models import (
    SearchIndexKnowledgeSource,
    KnowledgeSourceReference,
)

# 既存インデックスをナレッジソースとして作成
index_ks = SearchIndexKnowledgeSource(
    name="my-index-ks",
    description="既存の検索インデックス",
    index_name="my-existing-index",
)
index_client.create_or_update_knowledge_source(index_ks)

# ナレッジベースに両方のソースを紐付け
knowledge_base.knowledge_sources = [
    KnowledgeSourceReference(name="my-remote-sharepoint-ks"),
    KnowledgeSourceReference(name="my-index-ks"),
]
index_client.create_or_update_knowledge_base(knowledge_base)
```

**フィルタ式の例:**

| 目的 | フィルタ式 |
|---|---|
| 特定サイトに限定 | `Path:"https://contoso.sharepoint.com/sites/hr/Shared Documents"` |
| サイト ID で指定 | `SiteID:"00aa00aa-bb11-cc22-dd33-44ee44ee44ee"` |
| ファイルタイプ | `FileExtension:"docx" OR FileExtension:"pdf" OR FileExtension:"pptx"` |
| 日付範囲 | `LastModifiedTime >= 2024-01-01 AND LastModifiedTime <= 2025-12-31` |

#### (2) ナレッジベースの作成

作成したナレッジソースをナレッジベースに紐付けます：

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

> **注意**: ナレッジベース名は `.env` の `AZURE_SEARCH_KNOWLEDGE_BASE_NAME` に設定してください。

詳細は以下の公式ドキュメントを参照してください：
- [remote SharePoint Knowledge Source の作成](https://learn.microsoft.com/azure/search/agentic-knowledge-source-how-to-sharepoint-remote)
- [ナレッジベースの作成](https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-create-knowledge-base)

### 2. インストール

```bash
# 仮想環境の作成 (推奨)
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/macOS

# 依存パッケージのインストール (--pre フラグが必要)
pip install -r requirements.txt --pre
```

### 3. 環境変数の設定

```bash
cp .env.example .env
```

`.env` ファイルを編集して、以下の必須項目を設定してください：

| 変数名 | 説明 |
|---|---|
| `AZURE_AI_PROJECT_ENDPOINT` | Azure AI Foundry の Agent Service v2 プロジェクトエンドポイント |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | GPT-4o などのモデルデプロイメント名 |
| `AZURE_SEARCH_ENDPOINT` | Azure AI Search サービスエンドポイント |
| `AZURE_SEARCH_API_KEY` | Azure AI Search API キー |
| `AZURE_SEARCH_KNOWLEDGE_BASE_NAME` | ナレッジベース名 |

オプション設定：

```env
# SharePoint 検索の KQL フィルタ (特定サイト・ファイルタイプの絞り込み)
AZURE_SEARCH_SHAREPOINT_FILTER=FileExtension:"docx" OR FileExtension:"pdf"

# 最大結果数 (デフォルト: 10)
AZURE_SEARCH_TOP_K=10

# 最大ラウンド数 (デフォルト: 15)
DEEP_RESEARCH_MAX_ROUNDS=15
```

### 4. 認証

```bash
# Azure CLI でログイン
az login
```

---

## 使用方法

### 基本的な使い方

```bash
python main.py --query "2025年のクラウド移行計画を要約してください"
```

### 詳細オプション

```bash
# 出力ファイルを指定
python main.py --query "..." --output ./my_report.md

# 計画レビューを有効化 (研究計画を承認/修正してから実行)
python main.py --query "..." --plan-review

# 中間出力を非表示にして最終レポートのみ表示
python main.py --query "..." --no-stream

# デバッグログ有効化
python main.py --query "..." --verbose
```

### 出力

- `./outputs/research_<query>_<timestamp>.md` に Markdown レポートが保存されます
- レポートには以下が含まれます：
  - エグゼクティブサマリー
  - 重要な発見事項 (ソース引用付き)
  - 詳細分析
  - 推奨事項
  - ソース一覧
  - 信頼度・制限事項

---

## プロジェクト構造

```
maf-enterprise-deepresearch/
├── main.py                    # CLI エントリーポイント
├── requirements.txt           # 依存パッケージ
├── .env.example               # 環境変数テンプレート
├── README.md                  # このファイル
└── deep_research/
    ├── __init__.py            # パッケージ公開 API
    ├── config.py              # 設定ローダー
    ├── tools.py               # 検索ツール (Azure AI Search)
    └── workflow.py            # Magentic ワークフロー定義
```

---

## 使用技術

| コンポーネント | パッケージ / サービス |
|---|---|
| LLM オーケストレーション | `agent-framework` (Microsoft Agent Framework 1.0.0rc3) |
| Magentic パターン | `agent-framework-orchestrations` |
| Azure OpenAI 接続 | `AzureOpenAIResponsesClient` (Agent Service v2 / Responses API) |
| 社内ドキュメント検索 | `azure-search-documents` (Foundry IQ Knowledge Base + remote SharePoint) |
| 認証 | `azure-identity` (AzureCliCredential / DefaultAzureCredential) |

---

## 参考資料

- [Microsoft Agent Framework GitHub](https://github.com/microsoft/agent-framework)
- [Microsoft Agent Framework ドキュメント](https://learn.microsoft.com/en-us/agent-framework/)
- [Magentic Orchestration サンプル](https://github.com/microsoft/agent-framework/tree/main/python/samples/03-workflows/orchestrations)
- [参考リポジトリ: kushanon/Deep-Research-Agents](https://github.com/kushanon/Deep-Research-Agents)
