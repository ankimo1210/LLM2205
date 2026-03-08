# Local LLM Chat

ローカル LLM によるチャット MVP。vLLM + FastAPI + SQLite で動作し、ブラウザから利用できます。

## 機能

| 機能 | 説明 |
|------|------|
| チャット UI | `http://localhost:8000` をブラウザで開くだけ |
| ストリーミング | SSE によるトークン逐次表示 |
| 会話履歴 | SQLite に保存、サイドバーから再読込可能 |
| OpenAI 互換 | vLLM 以外の任意の OpenAI 互換 API に接続可能 |

## 前提

- Docker Desktop (WSL2 + Linux コンテナ)
- **GPU を使う場合**: NVIDIA GPU + NVIDIA Container Toolkit

## クイックスタート

### 1. 設定ファイルを作成

```bash
cp .env.example .env
# .env を編集して VLLM_MODEL_ID などを設定
```

### 2a. vLLM を使う（GPU 必須）

```bash
docker compose --profile with-vllm up
```

モデル初回ダウンロードに時間がかかります。`docker compose logs -f vllm` で進捗を確認してください。

### 2b. 外部 LLM API を使う（GPU 不要）

`.env` の `VLLM_BASE_URL` を外部 API のエンドポイントに変更してください。

| ツール | VLLM_BASE_URL 例 |
|--------|-----------------|
| LM Studio | `http://host.docker.internal:1234` |
| llama.cpp server | `http://host.docker.internal:8080` |
| Ollama | `http://host.docker.internal:11434/v1` |
| OpenAI | `https://api.openai.com` (VLLM_MODEL_ID=gpt-4o) |

```bash
docker compose up orchestrator
```

### 3. ブラウザで開く

```
http://localhost:8000
```

## 設定

`.env` で全て設定できます。

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `VLLM_BASE_URL` | `http://vllm:8001` | LLM API エンドポイント |
| `VLLM_MODEL_ID` | `Qwen/Qwen2.5-7B-Instruct` | モデル ID |
| `SYSTEM_PROMPT` | `You are a helpful assistant...` | システムプロンプト |
| `DATABASE_URL` | `sqlite:////data/chat.db` | SQLite パス |
| `HF_TOKEN` | (空) | gated モデル用 HuggingFace トークン |

## API

| Method | Path | 説明 |
|--------|------|------|
| `GET` | `/` | チャット UI |
| `POST` | `/chat` | メッセージ送信 (SSE レスポンス) |
| `GET` | `/conversations` | 会話一覧 |
| `GET` | `/conversations/{id}` | 会話履歴 |
| `GET` | `/health` | ヘルスチェック |

### POST /chat リクエスト形式

```json
{
  "conversation_id": "optional-uuid",
  "message": "こんにちは"
}
```

### SSE イベント形式

```
data: {"type": "start", "conversation_id": "abc123"}

data: {"type": "token", "content": "こんに"}

data: {"type": "token", "content": "ちは"}

data: {"type": "done"}
```

## 開発

```bash
# 依存関係インストール
pip install -e "apps/orchestrator[dev]"

# テスト実行
pytest apps/orchestrator/tests/ -v

# ローカル起動（vLLM が別途動いている場合）
cd apps/orchestrator
DATABASE_URL=sqlite:///./dev.db uvicorn app.main:app --reload
```

## アーキテクチャ

```
Browser (http://localhost:8000)
    │  HTTP + SSE
    ▼
FastAPI Orchestrator (:8000)
    │  ├── GET  /              → index.html (static)
    │  ├── POST /chat          → SSE stream
    │  ├── GET  /conversations → JSON
    │  └── GET  /health        → JSON
    │
    ├── SQLite (/data/chat.db)
    │     conversations, messages
    │
    └── vLLM OpenAI-compat API (:8001)
          POST /v1/chat/completions  (stream=true)
```

## ディレクトリ構成

```
local-chatgpt/
├── docker-compose.yml
├── .env.example
├── apps/
│   └── orchestrator/
│       ├── Dockerfile
│       ├── pyproject.toml
│       ├── app/
│       │   ├── main.py          # FastAPI エントリポイント
│       │   ├── config.py        # 設定 (pydantic-settings)
│       │   ├── db.py            # SQLAlchemy セットアップ
│       │   ├── models.py        # ORM モデル
│       │   ├── schemas.py       # Pydantic スキーマ
│       │   ├── llm_client.py    # vLLM HTTP クライアント
│       │   ├── routes/
│       │   │   ├── chat.py      # POST /chat (SSE)
│       │   │   └── conversations.py
│       │   ├── templates/
│       │   │   └── index.html   # チャット UI
│       │   └── static/
│       │       ├── styles.css
│       │       └── app.js
│       └── tests/
└── scripts/
    └── test_chat.sh
```
