# AtlasDataPlatform v1.0

**Marketing Intelligence Platform (AtlasDataPlatform)**

> Given today's market, audience and competitive landscape, what should marketers create next?

AtlasDataPlatform collects public marketing signals from **YouTube**, **Google Trends**, and **Reddit**, normalizes them into a single `MarketIntelligenceDataset`, engineers deterministic features, persists the result, and visualizes it.

No AI / LLM layer is included in v1.

---

## Architecture

```
Streamlit (thin UI)
        │
        ▼
DataCollectionEngine
        │
ProviderRegistry
   ┌────┼────┐
YouTube Trends Reddit
   └────┼────┘
        ▼
Validation → Feature Engineering
        ▼
MarketIntelligenceDataset
        ▼
StorageManager (local + Supabase)
        ▼
DuckDB Analytics → Plotly Dashboard
```

---

## Quick Start

```bash
cd atlas
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — add YOUTUBE_API_KEY, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET

streamlit run streamlit_app.py
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `YOUTUBE_API_KEY` | For YouTube | Google Cloud YouTube Data API v3 key |
| `REDDIT_CLIENT_ID` | For Reddit | Reddit app client ID |
| `REDDIT_CLIENT_SECRET` | For Reddit | Reddit app secret |
| `REDDIT_USER_AGENT` | Recommended | e.g. `AtlasDataPlatform/1.0 by username` |
| `SUPABASE_URL` / `SUPABASE_KEY` | Optional | Remote dataset storage |
| `ATLAS_CACHE_TTL_HOURS` | Optional | Default 24 |

On **Streamlit Community Cloud**, set the same keys in **Secrets**.

---

## Public Usage (Python)

```python
from atlas.engine import DataCollectionEngine
from atlas.storage import StorageManager

engine = DataCollectionEngine()
dataset = engine.collect("Artificial Intelligence")

storage = StorageManager()
storage.upload(dataset, dataset.topic)
```

---

## Project Structure

```
atlas/
├── streamlit_app.py          # Streamlit entry point
├── atlas/
│   ├── core/                 # Settings, models, contracts, secrets adapter
│   ├── providers/            # YouTube, Trends, Reddit + registry
│   ├── engine/               # Collector, validation, features
│   ├── storage/              # StorageManager
│   ├── analytics/            # DuckDB engine
│   └── utils/                # Logging
├── tests/
├── data/datasets/            # Local dataset cache
├── requirements.txt
└── README.md
```

---

## Deployment — Streamlit Community Cloud

1. Push this repository to GitHub.
2. Go to https://share.streamlit.io → New app.
3. Set main file: `streamlit_app.py`
4. Add secrets (same keys as `.env`).
5. Deploy.

---

## Tests

```bash
pytest tests/ -v
```

---

## Design Principles

- Domain models over providers
- Single public artifact: `MarketIntelligenceDataset`
- Providers are independent and fail in isolation
- Configuration only via `Settings`
- Streamlit is a thin client
- DuckDB never owns data
- Deterministic features only (no AI)

---

## License

Proprietary — AtlasDataPlatform
