# Wayfound — Smart Travel Planner

An AI travel planning agent. You describe a trip in natural language ("2 weeks in July, $1500, warm beach destination") and it returns a synthesized plan backed by an ML classifier, RAG over Wikivoyage articles, real weather data, and live currency rates.

Built for the AIE Bootcamp Week 4 project.

![Architecture](docs/architecture.svg)

---

## Table of contents

- [What it does](#what-it-does)
- [Architecture at a glance](#architecture-at-a-glance)
- [Tech stack](#tech-stack)
- [Project layout](#project-layout)
- [Running with Docker (one command)](#running-with-docker-one-command)
- [Running locally without Docker](#running-locally-without-docker)
- [Environment variables](#environment-variables)
- [The data — destinations.csv](#the-data--destinationscsv)
- [The ML model](#the-ml-model)
- [The RAG pipeline](#the-rag-pipeline)
- [The agent](#the-agent)
- [Auth flow](#auth-flow)
- [Cost per query](#cost-per-query)
- [Discord delivery](#discord-delivery)
- [LangSmith tracing](#langsmith-tracing)
- [Tests](#tests)
- [Engineering choices worth flagging](#engineering-choices-worth-flagging)
- [Limits and what's left](#limits-and-whats-left)

---

## What it does

You type a trip query in the browser. The backend:

1. Asks a small LLM (llama-3.1-8b) to extract structured info (budget, climate, etc.).
2. Sends the query to a LangGraph agent that decides which tools to call.
3. The agent has 4 tools:
   - **rag_tool** — searches a vector store of Wikivoyage destination articles.
   - **classifier_tool** — predicts a travel style (Adventure, Relaxation, Culture, Budget, Luxury, Family) using a scikit-learn model trained on 120 destinations.
   - **weather_tool** — calls OpenWeatherMap for current weather + 5-day forecast.
   - **fx_tool** — calls Open Exchange Rates for live currency conversion.
4. A bigger LLM (llama-3.3-70b) stitches the tool outputs into a natural-language travel plan.
5. The plan is saved to Postgres with full tool-call audit trail.
6. If a Discord webhook is configured, a copy is fired into the channel after the response is sent.

---

## Architecture at a glance

See `docs/architecture.svg` (rendered above). The short version:

- **Browser (React)** — sends JWT-protected requests, holds token in `localStorage`.
- **Backend (FastAPI, async)** — auth, request routing, agent orchestration.
- **LangGraph agent** — runs the tool loop with two Groq models.
- **Tools** — RAG (local), classifier (sklearn), weather (OpenWeatherMap), FX (Open Exchange Rates).
- **PostgreSQL + pgvector** — single source of truth for users, trips, tool_calls, and vector embeddings.
- **Discord webhook + LangSmith** — optional side channels (notification + tracing).

---

## Tech stack

| Layer | Choice |
|---|---|
| Backend | FastAPI (async) |
| Database | PostgreSQL 16 with pgvector extension |
| ORM / migrations | SQLAlchemy 2.x async + Alembic |
| ML | scikit-learn (RandomForest classifier) |
| Agent framework | LangGraph |
| LLMs | Groq (llama-3.1-8b-instant for extraction, llama-3.3-70b-versatile for synthesis) |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 (384-dim, runs locally — no OpenAI key needed) |
| Frontend | React 19 + Vite + Tailwind CSS |
| Auth | JWT (python-jose) + bcrypt |
| Containers | Docker Compose |
| Python env | uv |
| Tracing (optional) | LangSmith |
| Notifications (optional) | Discord webhook |

---

## Project layout

```
wayfound/
├── backend/           FastAPI app + Alembic + RAG + agent
│   ├── app/
│   │   ├── routes/        /health, /auth, /trips, /me
│   │   ├── agents/        LangGraph nodes, prompts, callbacks
│   │   ├── tools/         rag, classifier, weather, fx, tracker
│   │   ├── services/      auth, agent orchestration
│   │   ├── schemas/       Pydantic request/response models
│   │   ├── core/          settings, security, embeddings
│   │   ├── db/            SQLAlchemy engine + base
│   │   └── webhooks/      Discord delivery (fire-and-forget)
│   ├── alembic/           database migrations 001-005
│   ├── rag/               ingest + retrieval helpers
│   ├── tests/             pytest tests (TST-01, TST-02)
│   └── Dockerfile
├── frontend/          React + Vite + Tailwind chat UI
│   ├── src/
│   │   ├── pages/         LoginPage, ChatPage
│   │   ├── components/    ChatInput, MessageThread, ToolTracePanel, PrivateRoute
│   │   ├── contexts/      AuthContext (JWT + user state)
│   │   └── lib/           apiFetch wrapper
│   ├── nginx.conf         SPA + /api proxy for production
│   └── Dockerfile
├── ml-notebook/       Jupyter notebook that trained the classifier
│   ├── train.ipynb
│   └── train_executed.ipynb   (frozen output for reviewers)
├── data/              destinations.csv + Wikivoyage raw articles
├── models/            travel_classifier.joblib
├── results/           results.csv from training experiments
├── docs/              architecture.svg
└── docker-compose.yml
```

---

## Running with Docker (one command)

Easiest way. Requires Docker Desktop.

```bash
# from the repo root
docker compose up --build
```

What it brings up:

| Service | Port | What |
|---|---|---|
| `wayfound-pg` | 5432 | Postgres + pgvector with named volume `wayfound_pg_data` |
| `wayfound-backend` | 8000 | FastAPI (runs `alembic upgrade head` on startup) |
| `wayfound-frontend` | 5173 | nginx serving the production React build, proxying `/api` to the backend |

Then open **http://localhost:5173** in the browser.

> **Heads up — first build is slow** (~10 min). The backend image installs `torch` and pulls the sentence-transformers model on first request. After that, restarts are seconds.

To stop: `docker compose down`. To wipe the DB too: `docker compose down -v`.

---

## Running locally without Docker

You'll need: **Python 3.12**, **Node 20+**, **uv**, **Docker** (just for Postgres).

### 1. Start Postgres

```bash
docker run -d --name wayfound-pg \
  -e POSTGRES_USER=wayfound \
  -e POSTGRES_PASSWORD=wayfound \
  -e POSTGRES_DB=wayfound \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

### 2. Backend

```bash
cd backend
uv sync                                  # installs deps from pyproject.toml
cp .env.example .env                     # then fill in real keys (see below)
uv run alembic upgrade head              # creates all the tables
uv run python -m rag.ingest              # loads Wikivoyage articles into pgvector
uv run uvicorn app.main:app --reload     # starts the API on :8000
```

### 3. Frontend

In a separate terminal:

```bash
cd frontend
npm install
npm run dev          # starts Vite on :5173
```

### 4. Open

Visit **http://localhost:5173**, register an account, submit a trip query.

---

## Environment variables

Copy `backend/.env.example` to `backend/.env` and fill in:

| Var | Required? | Where to get it |
|---|---|---|
| `DATABASE_URL` | yes | `postgresql+asyncpg://wayfound:wayfound@localhost:5432/wayfound` |
| `JWT_SECRET_KEY` | yes | random 32+ char string (`python -c "import secrets; print(secrets.token_urlsafe(48))"`) |
| `JWT_ALGORITHM` | yes | `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | yes | `60` |
| `GROQ_API_KEY` | yes | https://console.groq.com/keys (free) |
| `OPENWEATHER_API_KEY` | optional | https://openweathermap.org (free, ~10 min activation lag) |
| `OPEN_EXCHANGE_RATES_APP_ID` | optional | https://openexchangerates.org/signup/free |
| `LANGSMITH_API_KEY` | optional | https://smith.langchain.com — enables agent tracing |
| `DISCORD_WEBHOOK_URL` | optional | Discord channel → Edit channel → Integrations → Webhooks |

If an optional key is missing, the matching tool returns a "not configured" note instead of crashing — the agent keeps going.

---

## The data — `destinations.csv`

The classifier was trained on a hand-curated dataset of **120 real travel destinations**, one row per city/region.

### How we built it

We started from a public Kaggle dataset of "Worldwide Travel Cities" with city ratings and climate, then **simulated a join** with a separate `economic_features_simulated.csv` to add cost-per-day and safety indices. This stand-in mock join lets us prototype the classifier with realistic-looking features without paying for a true commercial dataset.

> **For production:** the simulated join would be replaced with real sources — Numbeo (cost of living), Global Peace Index (safety), UN tourism statistics (crowd levels), TripAdvisor / Booking APIs (cultural site counts), etc. The pipeline (`Pipeline → ColumnTransformer → RandomForest`) does not need to change; only the inputs do.

### Columns

| Column | Type | Description |
|---|---|---|
| `name` | string | City/region name (Queenstown, Bali, Reykjavik…) |
| `country` | string | ISO country |
| `continent` | categorical | Continent — one-hot encoded by the pipeline |
| `cost_per_day_usd` | float | Average daily traveller spend |
| `avg_temp_celsius` | float | Mean annual temperature |
| `outdoor_activity_score` | int (0–10) | Hiking/water/adventure availability |
| `cultural_site_count` | int | Museums, monuments, UNESCO sites |
| `safety_index` | float | Higher = safer |
| `beach_access` | int (0/1) | Boolean — has coastline or major lake |
| `nightlife_score` | int (0–10) | Bars, clubs, late-night activity |
| `family_amenity_score` | float | Kid-friendly facilities |
| `crowd_level` | int (1–5) | 1 = empty, 5 = packed |
| `travel_style` | **label** | One of: `Adventure`, `Relaxation`, `Culture`, `Budget`, `Luxury`, `Family` |

### Labelling strategy

Labels were assigned by a deterministic rule-based pass over the feature columns (e.g. high `outdoor_activity_score` + low `cost_per_day_usd` → `Adventure`), then **manually adjusted** for clear edge cases. This is a *weak supervision* approach — for production you'd replace it with crowdsourced or expert-annotated labels.

### Class balance

All 6 classes are represented but not perfectly balanced. We address this with `class_weight='balanced'` inside the classifier and report **macro F1** (equal weight per class) as the primary metric instead of accuracy.

---

## The ML model

Trained in `ml-notebook/train.ipynb`. The frozen executed copy (`train_executed.ipynb`) is committed so reviewers can read the outputs without rerunning.

### Pipeline (no leakage)

```
ColumnTransformer(
  numeric features  → SimpleImputer(median) → StandardScaler
  categorical (continent) → SimpleImputer(most_frequent) → OneHotEncoder
)
   → RandomForestClassifier(class_weight='balanced')
```

Everything is inside one scikit-learn `Pipeline` so the imputer + scaler + encoder are fit **only on training folds during cross-validation** — no information leaks from validation rows.

### Models compared (Stratified 5-fold CV, 6 classes, F1-macro)

| Model | CV accuracy | CV F1-macro |
|---|---|---|
| Logistic Regression | 0.92 | 0.92 |
| Histogram Gradient Boosting | 0.92 | 0.92 |
| Random Forest (baseline) | 0.96 | 0.96 |
| **Random Forest (tuned)** | **0.98** | **0.98** |

Tuned with `GridSearchCV(scoring='f1_macro')` over:
- `n_estimators ∈ {100, 200, 300}`
- `max_depth ∈ {None, 5, 10, 20}`
- `min_samples_leaf ∈ {1, 2, 4}`

Best params: `n_estimators=300, max_depth=10, min_samples_leaf=1`.

### Why we picked Random Forest

- Strong out-of-the-box performance on small tabular data with mixed numeric/categorical features.
- Robust to outliers and unscaled features (we still scale for fair comparison with linear models).
- Built-in feature importance — useful for sanity-checking that `outdoor_activity_score` matters more than `name` (it does).

### Deterministic / reproducible

- `random_state=42` everywhere (split, CV, RF).
- `results.csv` records every experiment with timestamp, seed, params.
- `models/travel_classifier.joblib` is the frozen winner — loaded once at backend startup as a singleton.

> **sklearn version pin (1.4.2):** the model was trained on sklearn 1.4.2. Pickle stores class references, so the runtime needs the same version to deserialise. The backend pins it. For long-term production we'd export to ONNX or PMML to remove this lock.

---

## The RAG pipeline

### Source data

15 destination articles fetched from **Wikivoyage** via the MediaWiki API, stored as `.txt` files under `data/raw/wikivoyage/`. Each file is one destination:

```
Bali.txt, Bangkok.txt, Barcelona.txt, Cape_Town.txt, Chiang_Mai.txt,
Istanbul.txt, Kyoto.txt, Lisbon.txt, Maldives.txt, New_York_City.txt,
Paris.txt, Reykjavik.txt, Rome.txt, Tokyo.txt, Vienna.txt
```

### Chunking — parent + child

Each article is split twice:

| Layer | Token target | Overlap | Purpose |
|---|---|---|---|
| **Parent** | ~400 | 50 | Long enough to give the LLM real context |
| **Child** | ~100 | 50 | Short enough for *precise* similarity matches |

Each child carries its parent's UUID. At query time we search **child** vectors (precision), then return the **parent** content (context). This is a classic *parent-document retrieval* pattern.

### Embeddings — local, free

- Model: **`sentence-transformers/all-MiniLM-L6-v2`** (384-dim).
- Runs on CPU. ~80MB model file cached locally on first run.
- Loaded into memory once at backend startup as a singleton (`LocalEmbedder`).

We previously used OpenAI's `text-embedding-ada-002` (1536-dim, paid). We switched to MiniLM because the project budget is zero and ~85% retrieval quality on travel docs is more than enough for 15 destinations.

### Where vectors are stored

**Inside the same Postgres database**, in the `chunks` table.

```
chunks(
  id           UUID PK,
  destination  text,
  section      text,
  chunk_index  int,
  parent_id    UUID,           -- NULL for parents
  content      text,
  embedding    vector(384)     -- pgvector type
)
```

There is **no separate vector database** (no Chroma, Pinecone, Weaviate). One Postgres for relational + vector. Why:

- The Week 4 spec requires it (avoids filesystem-backed vector store).
- One DB connection, one set of migrations, one backup.
- The pgvector extension supports HNSW indexing — competitive with dedicated vector DBs at this scale.

### Indexing — HNSW

```sql
CREATE INDEX ix_chunks_embedding_hnsw
  ON chunks USING hnsw (embedding vector_cosine_ops)
  WITH (m=16, ef_construction=64);
```

- `m=16` — number of bi-directional links per node.
- `ef_construction=64` — quality of graph during build.
- `vector_cosine_ops` — cosine distance (we normalize embeddings).

These are the standard balanced settings for ~225-row corpora. At this scale even a brute-force scan would be fast, but we use HNSW so the query path stays the same as it would at 100k+ rows.

### Retrieval flow

1. Embed the user's query with the same MiniLM model (384-dim).
2. SQL `ORDER BY embedding <=> :query_vec LIMIT top_k * 3` over **child** chunks.
3. Walk the children in hit order, dedupe by `parent_id`, take the first `top_k`.
4. Fetch those parent chunks from the same table by `id IN (...)`.
5. Return `[{id, destination, section, content, score}]` to the agent.

`score` is the rank position (0 = closest hit), not raw cosine distance — keeps the API stable if we swap the metric later.

### Resilience

`ensure_indexed()` runs on backend startup. It checks if the `chunks` table is already populated; if so, it skips ingest. If embeddings fail, it logs a warning and keeps the app booting — the RAG tool will gracefully return an empty list rather than 500-ing.

---

## The agent

Built with **LangGraph** in `app/agents/`.

### Node graph

```
START → extract_node → tools_loop → END
```

- **extract_node** — the cheap 8b model rewrites the user's free-text query into structured fields (budget, duration, climate, prefs[]). On failure, it falls back to passing the raw query through.
- **tools_loop** — the 70b model reads the conversation, decides whether to call a tool, and emits a tool call or a final answer. We bind exactly the 4 tools above with `agent_llm.bind_tools(tools)`.
- **Custom `tools_node`** — runs the chosen tool, validates inputs against its Pydantic schema, persists a `ToolCall` row with input/output/latency, and feeds the result back into the loop.

### Allowlist enforcement

`agent_llm.bind_tools([rag, classifier, weather, fx])` is the only place tools are exposed. If the LLM hallucinates a tool name (e.g. `flights_tool` after we removed it), the custom `tools_node` returns:

```
Error: tool 'flights_tool' is not in the allowlist.
Available: rag_tool, classifier_tool, weather_tool, fx_tool.
```

This is a **string** the LLM sees, not an exception — it can recover and pick a valid tool.

### Token + cost callback

`app/agents/callbacks.py` hooks into LangChain's callback system to:
- Sum `prompt_tokens` + `completion_tokens` per LLM call.
- Multiply by Groq's published per-token price.
- Log per-step `token_usage model=… prompt=… completion=… cost_usd=…`.

These logs feed the cost-per-query table below.

---

## Auth flow

1. **POST /auth/register** — creates user with bcrypt-hashed password.
2. **POST /auth/login** — verifies password, returns a JWT (1h expiry).
3. Frontend stores JWT in `localStorage` under key `wayfound_token`.
4. On every protected request, frontend attaches `Authorization: Bearer <token>`.
5. **GET /me** — used after page refresh to rehydrate user state from the token.

JWT secret never leaves the server. Browser only ever sees the token (which carries only the user's UUID and an expiry).

The auth scheme advertised to Swagger UI is `HTTPBearer` (not `OAuth2PasswordBearer`) — it gives a single "paste the token" Authorize button that works with our JSON-body login route.

---

## Cost per query

Measured from real Groq logs:

| Model | Tokens (avg) | $ per query (approx) |
|---|---|---|
| llama-3.1-8b-instant (extraction) | ~750 in / 50 out | $0.00004 |
| llama-3.3-70b-versatile (agent + synthesis, 3-4 calls) | ~10,000 in / 300 out | $0.006 |
| **Total per query** | **~12k tokens** | **~$0.006** |

Free-tier daily limit on llama-3.3-70b: **100,000 tokens/day** ≈ 15-20 full queries before reset.

---

## Discord delivery

When `DISCORD_WEBHOOK_URL` is set, every successful trip plan posts a copy to that Discord channel.

**Crucially: it's fire-and-forget.** The HTTP response is sent to the user *before* the Discord call runs. Implementation lives in `app/webhooks/discord.py` and is dispatched via FastAPI `BackgroundTasks`. Discord being down or slow has zero impact on user-facing latency or reliability — it just logs a warning server-side.

To enable: pick a Discord channel → Edit Channel → Integrations → Webhooks → New Webhook → copy URL → paste into `.env`.

---

## LangSmith tracing

When `LANGSMITH_API_KEY` is set, every agent run is logged as a tree on `https://smith.langchain.com` under project `wayfound`. You see:

- Each LLM call (extraction → planning → synthesis) with inputs, outputs, token counts.
- Each tool call with arguments, return value, latency.
- Total cost per trace.
- Re-runnable playground for debugging prompts.

This is wired up via env vars only — no code changes needed.

---

## Tests

`backend/tests/` — run with `uv run pytest -v` from `backend/`.

| File | Covers | Requirement |
|---|---|---|
| `test_schemas.py` | RegisterRequest / LoginRequest / PlanTripRequest validation (good + bad input) | TST-02 |
| `test_tools_isolation.py` | weather_tool and fx_tool gracefully degrade when their API key is missing | TST-01 |
| `conftest.py` | Sets dummy env vars before app code imports `Settings()` |  |

E2E test (TST-03 — full agent run with mocked LLMs) is scaffolded but not finished — see "Limits" below.

---

## Engineering choices worth flagging

- **Async all the way.** Every external call (LLM, DB, weather, FX) uses async clients. No `requests.get`, no `time.sleep` in request paths.
- **Settings validated at startup.** Backend refuses to start if a required env var is missing — better than 500-ing on first request.
- **Tools fail soft, not hard.** A missing API key returns a stub note; the agent keeps running.
- **Pydantic at every boundary.** Request bodies, response bodies, tool inputs, LLM extraction outputs — all validated.
- **HTTPBearer for /docs.** Swap from `OAuth2PasswordBearer` because Swagger's auto-login can't talk to JSON-body login routes.
- **One Postgres for everything.** Users, trips, tool call logs, **and** vector embeddings — all in the same DB via pgvector.
- **DI everywhere.** ML model, embedding client, DB session, current user — every dependency comes through FastAPI `Depends()` or LangGraph state.
- **Lifespan singletons.** Heavy objects (sklearn Pipeline, sentence-transformers model, ChatGroq instances, DB engine) are created once in `lifespan` and reused.

---

## Limits and what's left

- **Flights tool** was removed — Amadeus signup wasn't reachable during build. Tool slot is left empty; agent now exposes 4 tools, not 5.
- **TST-03 E2E test** is scaffolded but not finished. Would mock both Groq calls and assert the trip persists with correct shape.
- **Frontend has only chat + login pages** — no trip history view yet.
- **Classifier sklearn lock** — tied to 1.4.2 because that's what the model was pickled with. Re-train on a current sklearn or export to ONNX to remove the pin.
- **No streaming responses** — answers come back all at once. LangGraph supports streaming; the UI doesn't wire it up yet.
- **OpenWeather has a ~10-minute activation lag** for new keys; 401 responses during that window are handled gracefully but produce empty weather data.

---

## License

Bootcamp project — use at your own risk.