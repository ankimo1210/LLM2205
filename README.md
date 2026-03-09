# Local LLM Chat

ローカル LLM によるセルフホスト型チャット MVP。
vLLM (または任意の OpenAI 互換 API) + FastAPI + SQLite で動作し、ブラウザからすぐに使えます。

## 機能

- ブラウザベースのチャット UI（`http://localhost:8000`）
- SSE によるストリーミング応答
- ブラウザ上でのモデル選択（`/v1/models` から自動取得）
- SQLite による会話履歴の永続化
- サイドバーから過去会話を選択して再読込
- 会話ごとのトークン使用量（prompt / completion / total）を表示
- vLLM / LM Studio / Ollama / OpenAI など任意の OpenAI 互換バックエンドに接続可能

## 前提条件

| 必須 | バージョン |
|------|-----------|
| Docker Desktop | WSL2 バックエンド + Linux コンテナモード |
| docker compose | v2（Docker Desktop 同梱） |

**GPU を使う場合（vLLM 内蔵モード）のみ追加で必要:**

- NVIDIA GPU（VRAM 8 GB+推奨）
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

---

## クイックスタート（コピペで OK）

### 方法 A — 外部 LLM API を使う（GPU 不要、最も手軽）

LM Studio / Ollama / OpenAI など既に動いている API がある場合:

```bash
git clone https://github.com/<your-user>/local-chatgpt.git
cd local-chatgpt
cp .env.example .env
```

`.env` を編集して `VLLM_BASE_URL` を書き換える:

```dotenv
# Ollama の場合
VLLM_BASE_URL=http://host.docker.internal:11434
VLLM_MODEL_ID=llama3

# LM Studio の場合
VLLM_BASE_URL=http://host.docker.internal:1234
VLLM_MODEL_ID=local-model

# OpenAI の場合
VLLM_BASE_URL=https://api.openai.com
VLLM_MODEL_ID=gpt-4o
```

> **Note:** `/v1` は不要です。コードが自動で `/v1/chat/completions` を付与します。

```bash
docker compose up --build -d
```

### 方法 B — vLLM を使う（GPU 必須）

```bash
git clone https://github.com/<your-user>/local-chatgpt.git
cd local-chatgpt
cp .env.example .env
# .env の VLLM_MODEL_ID を必要に応じて変更

docker compose --profile with-vllm up --build -d
```

> **初回はモデルダウンロードに時間がかかります。**
> 進捗確認: `docker compose logs -f vllm`

### ブラウザで開く

```
http://localhost:8000
```

---

## 動作確認（curl）

```bash
# ヘルスチェック
curl http://localhost:8000/health
# → {"status":"ok"}

# チャット（SSE ストリーム）
curl -sN http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "こんにちは！"}'

# 会話一覧
curl http://localhost:8000/conversations

# 特定の会話の履歴（id は上の一覧から取得）
curl http://localhost:8000/conversations/<conversation_id>
```

スモークテスト用スクリプトもあります:

```bash
bash scripts/test_chat.sh
```

---

## ブラウザ UI の使い方

1. `http://localhost:8000` を開く
2. テキスト入力欄にメッセージを入力し **送信** (または **Enter**)
3. 応答がストリーミング表示される（「生成中…」インジケータ付き）
4. **Shift+Enter** で改行
5. サイドバーの **＋ New Chat** で新しい会話を開始
6. サイドバーの過去会話をクリックして履歴を再読込

---

## 設定 (.env)

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `VLLM_BASE_URL` | `http://vllm:8001` | LLM API エンドポイント（`/v1` 不要） |
| `VLLM_MODEL_ID` | `Qwen/Qwen2.5-7B-Instruct` | モデル ID |
| `SYSTEM_PROMPT` | `You are a helpful assistant...` | システムプロンプト（フォールバック） |
| `SYSTEM_PROMPT_FILE` | *(empty)* | システムプロンプトファイルパス（指定時優先） |
| `DATABASE_URL` | `sqlite:////data/chat.db` | SQLite パス (コンテナ内) |
| `HF_TOKEN` | *(空)* | gated モデル用 HuggingFace トークン |

### システムプロンプトのカスタマイズ

全モデル共通のシステムプロンプトは `prompts/system_prompt.md` で管理できます。
Markdown 形式で複数行の指示を書けます。

```bash
# 編集するだけで次のリクエストから反映されます（コンテナ再起動不要）
$EDITOR prompts/system_prompt.md
```

優先順位: `SYSTEM_PROMPT_FILE` のファイルが存在する場合 → その内容を使用。ファイルがない場合 → `.env` の `SYSTEM_PROMPT` にフォールバック。

---

## API

| Method | Path | 説明 |
|--------|------|------|
| `GET` | `/` | チャット UI (HTML) |
| `POST` | `/chat` | メッセージ送信 → SSE ストリーム応答 |
| `GET` | `/models` | 利用可能なモデル一覧 (JSON) |
| `GET` | `/conversations` | 会話一覧 (JSON) |
| `GET` | `/conversations/{id}` | 会話履歴 (JSON) |
| `GET` | `/health` | ヘルスチェック |

### POST /chat

```json
{
  "conversation_id": "optional-uuid",
  "model": "llama3.1:8b",
  "message": "こんにちは"
}
```

`model` は省略可。省略時は `.env` の `VLLM_MODEL_ID` が使われます。

### SSE イベント

```
data: {"type": "start", "conversation_id": "abc123", "model": "llama3.1:8b"}

data: {"type": "token", "content": "こんに"}

data: {"type": "token", "content": "ちは"}

data: {"type": "done"}
```

`done` イベントにはバックエンドが返す usage 情報が含まれます（対応している場合）:

```
data: {"type": "done", "usage": {"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168}}
```

> **Note:** トークン使用量の取得には `stream_options.include_usage` に対応したバックエンドが必要です（vLLM, OpenAI, 新しい Ollama など）。未対応の場合 `usage` は省略されます。

エラー時:

```
data: {"type": "error", "message": "Cannot reach LLM endpoint at ..."}
```

---

## アーキテクチャ

```
Browser (:8000)
    │  HTTP + SSE
    ▼
FastAPI Orchestrator (:8000)
    │  ├── GET  /              → index.html
    │  ├── POST /chat          → SSE stream
    │  ├── GET  /conversations → JSON
    │  └── GET  /health        → JSON
    │
    ├── SQLite (/data/chat.db)
    │     conversations, messages
    │
    └── OpenAI-compat LLM API (:8001 / external)
          POST /v1/chat/completions  (stream=true)
```

---

## ディレクトリ構成

```
local-chatgpt/
├── docker-compose.yml        # orchestrator + vLLM (profile) + Caddy (profile)
├── Caddyfile                 # reverse proxy 設定 (optional)
├── .env.example              # 環境変数テンプレート
├── .github/workflows/ci.yml  # GitHub Actions (ruff + pytest)
├── scripts/
│   └── test_chat.sh          # curl スモークテスト
└── apps/orchestrator/
    ├── Dockerfile
    ├── pyproject.toml
    ├── app/
    │   ├── main.py            # FastAPI エントリポイント
    │   ├── config.py          # pydantic-settings
    │   ├── db.py              # SQLAlchemy engine
    │   ├── models.py          # ORM (Conversation, Message)
    │   ├── schemas.py         # Pydantic スキーマ
    │   ├── llm_client.py      # httpx streaming client
    │   ├── routes/
    │   │   ├── chat.py        # POST /chat (SSE)
    │   │   └── conversations.py
    │   ├── templates/
    │   │   └── index.html
    │   └── static/
    │       ├── styles.css
    │       └── app.js
    └── tests/
        ├── conftest.py
        ├── test_health.py
        └── test_conversations.py
```

---

## 開発

```bash
# 依存関係インストール
pip install -e "apps/orchestrator[dev]"

# テスト
cd apps/orchestrator
pytest tests/ -v

# Lint
ruff check app/ tests/

# ローカル起動（外部 LLM が動いている場合）
DATABASE_URL=sqlite:///./dev.db \
VLLM_BASE_URL=http://localhost:11434 \
VLLM_MODEL_ID=llama3 \
uvicorn app.main:app --reload
```

---

## LAN 内の他端末からアクセスする

Uvicorn は `0.0.0.0` で listen しており、Docker Desktop はホストの全インターフェースにポートを公開するため、
**追加設定なしで** 同一 LAN 内の他デバイス（スマホ・別 PC）からアクセスできます。

### 1. Windows ホストの IP を確認する

PowerShell で:

```powershell
# Wi-Fi の場合
(Get-NetIPAddress -InterfaceAlias "Wi-Fi" -AddressFamily IPv4).IPAddress

# 有線 LAN の場合
(Get-NetIPAddress -InterfaceAlias "Ethernet" -AddressFamily IPv4).IPAddress

# よく分からない場合（全アダプタ一覧）
Get-NetIPAddress -AddressFamily IPv4 | Select-Object InterfaceAlias, IPAddress
```

たとえば `192.168.1.100` が返ったら、別端末のブラウザで:

```
http://192.168.1.100:8000
```

### 2. Windows Firewall の注意

Docker Desktop on WSL2 は通常、自動でファイアウォール規則を追加します。
もしアクセスできない場合は、ポート 8000 を手動で許可してください:

```powershell
# 管理者権限の PowerShell で実行
New-NetFirewallRule -DisplayName "LocalLLMChat" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

不要になったら削除:

```powershell
Remove-NetFirewallRule -DisplayName "LocalLLMChat"
```

---

## 外部公開（インターネット経由）

> **⚠️ 重要:** このアプリにはユーザー認証がありません。
> インターネットに直接公開すると、**誰でも LLM を呼び出せてしまいます**。
> 必ず以下のいずれかの対策を取ってください。

### 推奨: 安全な外部アクセス方法

| 方法 | 難易度 | 特徴 |
|------|--------|------|
| **Tailscale** | ★☆☆ | VPN 越しにプライベートアクセス。設定が最も簡単。ポート開放不要 |
| **Cloudflare Tunnel** | ★★☆ | 無料で HTTPS + ドメイン。Cloudflare Zero Trust で認証も追加可能 |
| **Caddy + Basic Auth** | ★★☆ | このリポジトリに同梱。下記参照 |

### Caddy リバースプロキシ（同梱・optional）

HTTPS 化・Basic Auth・SSE 互換の reverse proxy として Caddy を同梱しています。

#### 起動方法

```bash
docker compose --profile with-caddy up -d
```

`http://<host-ip>` (ポート 80) でアクセスできます。

#### Basic Auth を有効にする

1. ハッシュ化パスワードを生成:

```bash
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'YOUR_PASSWORD'
```

2. [Caddyfile](Caddyfile) の `basicauth` ブロックのコメントを外し、ハッシュを貼り付ける:

```
basicauth /* {
    admin $2a$14$xxxxxxxxxxxxxxxxxxxx
}
```

3. 再起動:

```bash
docker compose --profile with-caddy restart caddy
```

#### HTTPS（独自ドメイン）

[Caddyfile](Caddyfile) の `:80` をドメイン名に変更するだけで、Caddy が自動で Let's Encrypt 証明書を取得します:

```
chat.example.com {
    ...
}
```

> **SSE の注意:** Caddy 設定には `flush_interval -1` を入れてあり、SSE ストリーミングがバッファリングされずにそのまま動作します。
> nginx など他のプロキシを使う場合は、`proxy_buffering off` / `X-Accel-Buffering: no` の設定が必要です。

---

## トラブルシューティング

### Docker が GPU を認識しない

```
docker: Error response from daemon: could not select device driver
```

→ [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) をインストールしてください。
WSL2 の場合は **Windows ホスト側に** NVIDIA ドライバを入れ、WSL 側に Container Toolkit を入れます。

```bash
# 確認
nvidia-smi              # WSL 内で GPU が見えるか
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

### WSL から VS Code で開きたい

```bash
cd /home/<user>/local-chatgpt
code .
```

Windows 側で VS Code + Remote WSL 拡張機能がインストールされていれば自動接続します。

### ポート 8000 / 8001 が競合する

```bash
# 何が使っているか確認
lsof -i :8000
# または docker-compose.yml のポートマッピングを変更:
#   ports: ["8080:8000"]
```

### モデルダウンロードに時間がかかる

vLLM は初回起動時に HuggingFace からモデルをダウンロードします（7B で数 GB〜）。
`hf_cache` Docker volume にキャッシュされるため **2回目以降は高速** です。

```bash
docker compose logs -f vllm   # 進捗を確認
```

### vLLM 起動前に orchestrator がエラーになる

orchestrator は vLLM の healthcheck 完了を待って起動します（`depends_on.condition: service_healthy`）。
外部 API モードではこの依存は無視されます（`required: false`）。

vLLM が healthy になるまで最大 **7.5 分**（`start_period: 180s` + `interval × retries`）待ちます。
大きなモデルの場合は `docker-compose.yml` の `start_period` を増やしてください。

手動で vLLM の状態を確認:

```bash
curl http://localhost:8001/health
```

### orchestrator が「Cannot reach LLM endpoint」と返す

`.env` の `VLLM_BASE_URL` がコンテナ内から到達可能か確認してください。

| 状況 | 正しい URL |
|------|-----------|
| vLLM と同じ compose | `http://vllm:8001` |
| ホスト上の LM Studio / Ollama | `http://host.docker.internal:<port>` |
| 外部サーバー | `http://<ip>:<port>` |

`localhost` はコンテナ自身を指すため使えません。

---

## ライセンス

MIT
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
