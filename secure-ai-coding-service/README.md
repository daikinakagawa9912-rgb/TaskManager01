# Secure AI Coding Service

MCPサーバーを用いたセキュアなAIコーディングサービスです。  
ユーザーが入力した CREATE 文を **抽象化** してから Claude に渡すことで、
実際のテーブル名・カラム名を LLM に一切開示せずに SQL を自動生成します。

---

## 全体アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│                        Web UI (Browser)                         │
│   CREATE文 + 抽出要件 ──→ [SQL を生成する] ──→ 最終SQL 表示    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ POST /api/generate-sql
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  MCP Server (FastAPI / Python)                  │
│                                                                 │
│  1. parser.py      : CREATE文を解析しテーブル・カラム情報抽出   │
│  2. abstractor.py  : 実名 → 抽象名 (Table01/Column01...) 変換  │
│  3. mcp_server.py  : 抽象スキーマ + 要件JSON 組み立て          │
│  4. claude_client.py: 抽象情報のみを Claude に送信             │
│  5. restorer.py    : 抽象SQL → 実SQL に復元                    │
│                                                                 │
│  ※ 実テーブル/カラム名は MCP Server 内部にのみ保持            │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Anthropic API (抽象情報のみ)
                           ▼
                    Claude Sonnet 4.x
                    (抽象 SQL を生成)
```

---

## 処理フロー詳細

| # | フェーズ | 説明 |
|---|---------|------|
| 1 | 入力受付 | Web UI から CREATE 文と抽出要件を受け取る |
| 2 | パース | `parser.py` が CREATE 文を解析し、テーブル/カラム/FK 情報を抽出 |
| 3 | 抽象化 | `abstractor.py` が `Table01/Column01` 形式にマッピング（内部保持） |
| 4 | 要件変換 | 自然言語要件を抽象名の JSON に変換 |
| 5 | Claude 呼び出し | **抽象スキーマ + 抽象要件 JSON のみ**を Claude に送信 |
| 6 | 抽象 SQL 受信 | Claude が抽象名を使った SQL を返す |
| 7 | 復元 | `restorer.py` が抽象名を実名に置換 |
| 8 | 返却 | 最終 SQL を Web UI に返す |

---

## ディレクトリ構成

```
secure-ai-coding-service/
├── backend/
│   ├── main.py           # FastAPI エントリーポイント・API エンドポイント
│   ├── mcp_server.py     # MCP パイプライン全体の制御
│   ├── parser.py         # CREATE TABLE 文パーサー
│   ├── abstractor.py     # 抽象化ロジック
│   ├── restorer.py       # 復元ロジック
│   ├── claude_client.py  # Claude API クライアント
│   ├── models.py         # Pydantic データモデル
│   ├── requirements.txt  # Python 依存パッケージ
│   └── tests/
│       └── test_pipeline.py  # 単体テスト
└── frontend/
    ├── index.html        # Web UI
    ├── style.css         # スタイルシート
    └── app.js            # フロントエンドロジック
```

---

## セットアップ

### 前提条件
- Python 3.11 以上
- Anthropic API キー（`ANTHROPIC_API_KEY`）

### インストール

```bash
cd secure-ai-coding-service/backend
pip install -r requirements.txt
```

### 環境変数

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Windows (PowerShell):
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

### サーバー起動

```bash
cd secure-ai-coding-service/backend
uvicorn main:app --reload --port 8000
```

ブラウザで `http://localhost:8000` を開くと Web UI が表示されます。

### テスト実行

```bash
cd secure-ai-coding-service/backend
python -m pytest tests/ -v
```

---

## API 仕様

### `POST /api/generate-sql`

**リクエスト**

```json
{
  "create_statements": "CREATE TABLE users (...); CREATE TABLE departments (...);",
  "requirements": "ユーザーID\nユーザー番号\n部署名\nユーザー番号が1000以下なら「〇」、それ以外なら「×」"
}
```

`requirements` には自然言語テキストまたは抽象名形式の JSON 文字列を指定できます。

**レスポンス**

```json
{
  "sql": "SELECT users.user_id, users.user_no, departments.dept_name, ...",
  "abstracted_sql": "SELECT Table01.Column01, Table01.Column02, Table02.Column02, ..."
}
```

`abstracted_sql` はデバッグ用です。本番環境では API レスポンスから除外してください。

### `GET /api/health`

```json
{ "status": "ok" }
```

---

## 抽象化要件 JSON 仕様

Claude に渡される要件 JSON の構造：

```jsonc
{
  // SELECT 句：カラム参照またはCASE式の配列
  "select": [
    { "table": "Table01", "column": "Column01" },
    { "table": "Table01", "column": "Column02" },
    { "table": "Table02", "column": "Column02" },
    {
      "case": {
        "when": [
          { "condition": "Table01.Column02 <= 1000", "value": "〇" }
        ],
        "else": "×",
        "alias": "user_flag"
      }
    }
  ],

  // FROM 句：起点テーブル（抽象名）
  "from_table": "Table01",

  // JOIN 句（省略可）
  "joins": [
    {
      "type": "INNER",          // INNER / LEFT / RIGHT / FULL
      "table": "Table02",
      "on": "Table01.Column04 = Table02.Column01"
    }
  ],

  // WHERE 句（省略可）
  "where": "Table01.Column03 IS NOT NULL",

  // GROUP BY（省略可）
  "group_by": ["Table02.Column02"],

  // HAVING（省略可）
  "having": "COUNT(*) > 1",

  // ORDER BY（省略可）
  "order_by": ["Table01.Column01 ASC"],

  // DISTINCT（省略可、デフォルト false）
  "distinct": false
}
```

---

## Claude へのプロンプトテンプレート

```
You are an expert SQL query builder.
You will be given:
1. An abstract database schema (CREATE TABLE statements using abstract names only).
2. A JSON object describing the SQL query requirements using the same abstract names.

Your task:
- Generate a single, syntactically correct SQL SELECT statement.
- Use ONLY the abstract table and column names from the schema.
- Do NOT invent, rename, or guess any identifiers.
- Do NOT output any explanation, markdown fences, or commentary – output the raw SQL only.

## Abstract Schema

{abstract_schema}

## Requirements (JSON)

{requirements_json}

## Output

Output the SQL SELECT statement only.
```

---

## 動作シナリオ（具体例）

### 入力 CREATE 文

```sql
CREATE TABLE users (
  user_id   INT          NOT NULL,
  user_no   VARCHAR(10)  NOT NULL,
  name      VARCHAR(100),
  dept_id   INT,
  PRIMARY KEY (user_id),
  FOREIGN KEY (dept_id) REFERENCES departments(dept_id)
);

CREATE TABLE departments (
  dept_id   INT          NOT NULL,
  dept_name VARCHAR(100) NOT NULL,
  PRIMARY KEY (dept_id)
);
```

### 抽象化後のスキーマ（Claude に送るもの）

```sql
CREATE TABLE Table01 (
  Column01 INT NOT NULL,
  Column02 VARCHAR(10) NOT NULL,
  Column03 VARCHAR(100),
  Column04 INT,
  PRIMARY KEY (Column01),
  FOREIGN KEY (Column04) REFERENCES Table02(Column01)
);

CREATE TABLE Table02 (
  Column01 INT NOT NULL,
  Column02 VARCHAR(100) NOT NULL,
  PRIMARY KEY (Column01)
);
```

### 抽出要件 → 抽象化要件 JSON

```json
{
  "select": [
    { "table": "Table01", "column": "Column01" },
    { "table": "Table01", "column": "Column02" },
    { "table": "Table02", "column": "Column02" },
    {
      "case": {
        "when": [{ "condition": "Table01.Column02 <= 1000", "value": "〇" }],
        "else": "×",
        "alias": "user_flag"
      }
    }
  ],
  "from_table": "Table01",
  "joins": [
    { "type": "INNER", "table": "Table02", "on": "Table01.Column04 = Table02.Column01" }
  ]
}
```

### Claude が生成する抽象 SQL

```sql
SELECT
  Table01.Column01,
  Table01.Column02,
  Table02.Column02,
  CASE WHEN Table01.Column02 <= 1000 THEN '〇' ELSE '×' END AS user_flag
FROM Table01
INNER JOIN Table02 ON Table01.Column04 = Table02.Column01
```

### 復元後の最終 SQL（Web UI に表示）

```sql
SELECT
  users.user_id,
  users.user_no,
  departments.dept_name,
  CASE WHEN users.user_no <= 1000 THEN '〇' ELSE '×' END AS user_flag
FROM users
INNER JOIN departments ON users.dept_id = departments.dept_id
```

---

## セキュリティ要件

| 要件 | 実装方法 |
|------|---------|
| 実名を Claude に渡さない | `abstractor.py` が変換、`claude_client.py` は抽象情報のみ受け取る |
| 推測・補完禁止 | Claude プロンプトで明示的に禁止 |
| マッピングの内部保持 | `mcp_server.py` 内でのみ `AbstractionMapping` を生成・使用 |
| ログに実名を残さない | `logger.info()` は抽象名のみ記録（`mcp_server.py` 参照） |
| リーク検出 | `restorer.validate_no_real_names_leaked()` で Claude 出力を検証 |

---

## 拡張案

| 機能 | 実装方針 |
|------|---------|
| 多段 JOIN | `joins` 配列を複数要素にするだけで対応済み |
| 集約 (GROUP BY / HAVING) | 要件 JSON の `group_by` / `having` フィールドを使用 |
| DISTINCT | `distinct: true` フラグ |
| サブクエリ | 要件 JSON に `subquery` キーを追加し、Claude プロンプトに説明を追記 |
| セッション管理 | リクエスト ID をキーに `AbstractionMapping` をキャッシュ（Redis 等） |
| 監査ログ | 抽象化要件 JSON のみを構造化ログ（JSON Lines）で保存 |
| スキーマバリデーション | 生成 SQL を sqlparse でパースして抽象名の整合性を確認 |
