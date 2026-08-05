"""
AtlasDataPlatform — Streamlit entry point.
Thin UI only. All business logic lives in the engine/providers.
"""

from __future__ import annotations

import json
from typing import Optional

import streamlit as st

# set_page_config MUST be the first Streamlit command.
# Accessing st.secrets / session before this can cause:
# "Tried to use SessionInfo before it was initialized"
st.set_page_config(
    page_title="AtlasDataPlatform — Marketing Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Secrets → env → Settings (after page config)
from atlas.core.secrets import apply_streamlit_secrets
from atlas.core.settings import get_settings

apply_streamlit_secrets()
get_settings.cache_clear()

from atlas.core.models import MarketIntelligenceDataset, ProgressStage
from atlas.engine.collector import DataCollectionEngine
from atlas.storage.manager import StorageManager
from atlas.analytics.duckdb_engine import DuckDBAnalyticsEngine
from atlas.utils.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("atlas.ui")


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

@st.cache_data(ttl=86400, show_spinner=False)
def load_cached_dataset(topic: str) -> Optional[dict]:
    storage = StorageManager()
    ds = storage.download(topic)
    if ds is None:
        return None
    return ds.model_dump(mode="json")


def save_and_cache(dataset: MarketIntelligenceDataset) -> str:
    storage = StorageManager()
    location = storage.upload(dataset, dataset.topic)
    load_cached_dataset.clear()
    return location


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def run_collection(topic: str, enabled_providers: list[str]) -> MarketIntelligenceDataset:
    progress_bar = st.progress(0.0, text="Starting collection…")
    status_box = st.empty()

    def on_progress(stage: ProgressStage, message: str, progress: float) -> None:
        progress_bar.progress(min(progress, 1.0), text=message)
        status_box.info(f"**{stage.value}** — {message}")

    engine = DataCollectionEngine(progress_callback=on_progress)
    dataset = engine.collect(topic, enabled_providers=enabled_providers)
    progress_bar.progress(1.0, text="Complete")
    return dataset


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

st.title("AtlasDataPlatform")
st.caption("AtlasDataPlatform · Content Supply · Search Demand · Community Voice")

with st.sidebar:
    st.header("Configuration")
    settings = get_settings()
    st.write(f"**Environment:** `{settings.atlas_env}`")
    st.write(f"**Schema:** `{settings.atlas_schema_version}`")
    st.write(f"**YouTube key:** {'✅' if settings.has_youtube_credentials else '❌'}")
    st.write(f"**Reddit creds:** {'✅' if settings.has_reddit_credentials else '❌'}")
    if settings.has_supabase_credentials:
        st.write("**Supabase:** 🟢 Connected")
    else:
        st.write("**Supabase:** 🟡 Local Mode (Supabase not configured)")
    st.divider()
    st.subheader("Providers")
    enable_youtube = st.checkbox("YouTube (Content Supply)", value=True)
    enable_trends = st.checkbox("Google Trends (Search Demand)", value=False)
    enable_reddit = st.checkbox("Reddit (Community Voice)", value=False)
    st.caption("Tip: leave Trends off on Streamlit Cloud if you hit Google 429 rate limits.")
    st.divider()
    st.markdown("Enter a topic and click **Analyze**.")

topic = st.text_input("Topic / Niche", value="Artificial Intelligence", placeholder="e.g. Artificial Intelligence")
col1, col2 = st.columns([1, 3])
with col1:
    analyze = st.button("Analyze", type="primary", use_container_width=True)
with col2:
    force_refresh = st.checkbox("Force refresh (ignore cache)", value=False)

dataset: Optional[MarketIntelligenceDataset] = None

if analyze and topic.strip():
    topic = topic.strip()
    enabled_providers: list[str] = []
    if enable_youtube:
        enabled_providers.append("youtube")
    if enable_trends:
        enabled_providers.append("google_trends")
    if enable_reddit:
        enabled_providers.append("reddit")

    if not enabled_providers:
        st.warning("Select at least one provider in the sidebar.")
    else:
        cached = None if force_refresh else load_cached_dataset(topic)
        if cached is not None:
            st.success("Loaded from cache (≤ 24 h)")
            dataset = MarketIntelligenceDataset.model_validate(cached)
        else:
            with st.spinner("Collecting marketing intelligence…"):
                try:
                    dataset = run_collection(topic, enabled_providers)
                    location = save_and_cache(dataset)
                    st.success(f"Collection complete — saved to `{location}`")
                    if location.startswith("supabase://"):
                        st.caption("Primary storage: Supabase")
                    else:
                        st.caption("Primary storage: local fallback")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Collection failed: {exc}")
                    logger.exception("UI collection error")
                    dataset = None

if dataset is not None:
    analytics = DuckDBAnalyticsEngine()
    stats = analytics.summary_stats(dataset)

    st.header("Overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Content Supply", stats.get("content_supply_count", 0))
    c2.metric("Search Demand", stats.get("search_demand_count", 0))
    c3.metric("Community Voice", stats.get("community_voice_count", 0))
    c4.metric("Duration (s)", f"{dataset.metadata.duration_seconds:.1f}")

    st.subheader("Provider Health")
    if dataset.provider_health:
        import pandas as pd
        health_df = pd.DataFrame([h.model_dump(mode="json") for h in dataset.provider_health])
        st.dataframe(health_df, use_container_width=True)
    else:
        st.info("No provider health data.")

    st.subheader("Feature Metrics")
    if dataset.derived_metrics:
        mcols = st.columns(4)
        for i, (k, v) in enumerate(dataset.derived_metrics.items()):
            mcols[i % 4].metric(k.replace("_", " ").title(), f"{v:,.4g}")
    else:
        st.info("No derived metrics.")

    st.header("Insights")
    tab1, tab2, tab3, tab4 = st.tabs(["Top Videos", "Rising Queries", "Top Communities", "Regional Interest"])

    with tab1:
        top_videos = stats.get("top_videos", [])
        if top_videos:
            import plotly.express as px
            import pandas as pd
            df = pd.DataFrame(top_videos)
            fig = px.bar(
                df, x="views", y="title", orientation="h",
                title="Top Videos by Views",
                hover_data=["channel", "engagement_rate"],
            )
            fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No video data.")

    with tab2:
        rising = stats.get("rising_queries", [])
        if rising:
            import pandas as pd
            st.dataframe(pd.DataFrame(rising), use_container_width=True)
        else:
            st.info("No rising queries.")

    with tab3:
        communities = stats.get("top_communities", [])
        if communities:
            import plotly.express as px
            import pandas as pd
            df = pd.DataFrame(communities)
            fig = px.bar(
                df, x="score", y="title", orientation="h",
                title="Top Discussions by Score",
                hover_data=["subreddit", "comments"],
            )
            fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No community data.")

    with tab4:
        regions = stats.get("top_regions", [])
        if regions:
            import plotly.express as px
            import pandas as pd
            df = pd.DataFrame(regions)
            fig = px.bar(df, x="region", y="interest", title="Interest by Region")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No regional data.")

    st.header("Export")
    payload = dataset.model_dump(mode="json")
    json_bytes = json.dumps(payload, indent=2, default=str).encode("utf-8")
    st.download_button(
        "Download JSON",
        data=json_bytes,
        file_name=f"atlas_{dataset.topic.replace(' ', '_')}.json",
        mime="application/json",
    )

    try:
        import pandas as pd
        if dataset.content_supply:
            csv = pd.DataFrame([v.model_dump(mode="json") for v in dataset.content_supply]).to_csv(index=False)
            st.download_button("Download Videos CSV", data=csv, file_name="content_supply.csv", mime="text/csv")
        if dataset.community_voice:
            csv = pd.DataFrame([d.model_dump(mode="json") for d in dataset.community_voice]).to_csv(index=False)
            st.download_button("Download Discussions CSV", data=csv, file_name="community_voice.csv", mime="text/csv")
    except Exception:
        pass
else:
    st.info("Enter a topic and click **Analyze** to begin.")
    st.markdown(
        """
**AtlasDataPlatform** collects public marketing signals from:
- **YouTube** → Content Supply
- **Google Trends** → Search Demand
- **Reddit** → Community Voice

Results are normalized into a single **MarketIntelligenceDataset**, enriched with deterministic features, and cached for 24 hours.
"""
    )
