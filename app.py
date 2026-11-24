"""Unstructured Legacy Ingestor — Streamlit UI.

Run with:  streamlit run app.py
Works fully offline. No API key required. Sample data is fictional.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

import streamlit as st

from ingestor import COMPANY
from ingestor.detect import detect_type
from ingestor.models import ExtractedRecord
from ingestor.paths import SAMPLES_DIR
from ingestor.pipeline import ingest_paths, ingest_samples
from ingestor.samples import VIN_ANITA_ACCORD

st.set_page_config(
    page_title="Unstructured Legacy Ingestor",
    page_icon="blueprint",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
  .block-container { padding-top: 1.4rem; max-width: 1280px; }
  .demo-banner {
    background: #fff6e5;
    border: 1px solid #e6d2a8;
    color: #5a4500;
    padding: 0.7rem 1rem;
    border-radius: 8px;
    font-size: 0.95rem;
    margin-bottom: 0.8rem;
  }
  .chunk-card {
    background: #fff;
    border: 1px solid #d5dbe3;
    border-left: 4px solid #1e3a5f;
    border-radius: 10px;
    padding: 0.75rem 0.9rem;
    margin: 0 0 0.7rem;
  }
  .chunk-kicker {
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #4a5a70;
    font-weight: 700;
    margin: 0 0 0.25rem;
  }
  .cite-pill {
    display: inline-block;
    background: #e8eef6;
    border: 1px solid #c5d0e0;
    border-radius: 999px;
    padding: 2px 10px;
    margin: 0 6px 6px 0;
    font-size: 0.8rem;
  }
  .status-ok { background: #e8f6f1; border-color: #b7ddd0; color: #1c4d3e; }
  .status-review { background: #fff6e5; border-color: #e6d2a8; color: #5a4500; }
  .status-rejected { background: #fdecea; border-color: #e8b4b4; color: #7a1f1f; }
  .raw-box {
    background: #f3f5f8;
    border: 1px solid #d5dbe3;
    border-radius: 8px;
    padding: 0.75rem 0.9rem;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.85rem;
    white-space: pre-wrap;
    line-height: 1.45;
  }
  h1 { letter-spacing: -0.02em; }
  div[data-testid="stMetric"] {
    background: #f3f5f8;
    border: 1px solid #d5dbe3;
    border-radius: 10px;
    padding: 8px 12px;
  }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

DEFAULT_QUERY = f"warranty claim transmission cooler line Anita Rosales VIN {VIN_ANITA_ACCORD}"

SAMPLE_CHOICES = {
    "All bundled samples": "all",
    "Scanned repair order (Lakeside Honda)": "repair-order-lakeside-honda.jpg",
    "Scanned deal recap (Lakeside Toyota)": "deal-recap-lakeside-toyota.jpg",
    "Scanned warranty claim (Lakeside Honda)": "warranty-claim-lakeside-honda.jpg",
    "Mainframe extract (CUSTDEAL.DAT + copybook)": "CUSTDEAL.DAT",
    "Messy service-history CSV": "service-history-export.csv",
    "Messy deal-register Excel": "deal-register-export.xlsx",
    "GM recall memo (plain text)": "gm-recall-memo.txt",
}


def _find_sample(name: str) -> Path | None:
    if name == "all":
        return None
    for path in SAMPLES_DIR.rglob(name):
        if path.is_file():
            return path
    return None


@st.cache_resource(show_spinner="Ingesting the sample files — OCR, mainframe, spreadsheets…")
def _ingest_cached():
    return ingest_samples(persist=True)


def _init_state() -> None:
    defaults = {
        "result": None,
        "query": DEFAULT_QUERY,
        "auto_searched": False,
        "hits": None,
        "pipeline_file": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _status_class(status: str) -> str:
    if status in {"ok", "review", "rejected"}:
        return f"status-{status}"
    return "cite-pill"


def _render_hits(hits) -> None:
    if not hits:
        st.info("No matches above the minimum score. Try a VIN, a claim number, or a customer name.")
        return
    for i, hit in enumerate(hits, start=1):
        chunk = hit.chunk
        st.markdown(
            f'<div class="chunk-card">'
            f'<div class="chunk-kicker">Citation [{i}] · score {hit.score:.2f}</div>'
            f'<div><span class="cite-pill">{escape(chunk.citation())}</span>'
            f'<span class="cite-pill">{escape(chunk.source_type)}</span></div>'
            f"<div>{escape(chunk.text)}</div>"
            "</div>",
            unsafe_allow_html=True,
        )


def _record_label(record: ExtractedRecord) -> str:
    bits = [record.source_file]
    if record.page is not None:
        bits.append(f"page {record.page}")
    if record.record_number is not None and record.source_type != "scan":
        bits.append(f"record {record.record_number}")
    bits.append(record.status)
    return " · ".join(bits)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
_init_state()

with st.sidebar:
    st.header("Sources")
    st.caption("Pick the bundled samples, or upload your own files. Nothing leaves this machine.")
    choice = st.selectbox("Bundled samples", list(SAMPLE_CHOICES.keys()), index=0)
    uploaded = st.file_uploader(
        "Or upload files",
        accept_multiple_files=True,
        type=["png", "jpg", "jpeg", "tif", "tiff", "pdf", "csv", "xlsx", "txt", "dat", "cpy"],
        help="For a mainframe extract, upload both the .DAT (or .ebc) file and its .CPY copybook.",
    )
    if st.button("Ingest selected", type="primary", use_container_width=True):
        st.session_state.auto_searched = False
        st.session_state.hits = None
        key = SAMPLE_CHOICES[choice]
        if uploaded:
            tmp = Path(st.session_state.get("_upload_dir") or "")
            import tempfile

            upload_root = Path(tempfile.mkdtemp(prefix="ingestor-upload-"))
            saved: list[Path] = []
            copybook = None
            for item in uploaded:
                dest = upload_root / item.name
                dest.write_bytes(item.getvalue())
                saved.append(dest)
                if dest.suffix.lower() in {".cpy", ".cob", ".cbl"}:
                    copybook = dest
            st.session_state.result = ingest_paths(saved, copybook_path=copybook, persist=False)
            st.success(f"Ingested {len(saved)} uploaded file(s).")
        elif key == "all":
            # Bypass the cache so a fresh click re-runs, but reuse cache on first load.
            _ingest_cached.clear()
            st.session_state.result = _ingest_cached()
        else:
            path = _find_sample(key)
            if path is None:
                st.error(f"Could not find sample {key}. Run `python -m ingestor generate` first.")
            else:
                copybook = SAMPLES_DIR / "mainframe" / "CUSTDEAL.CPY"
                st.session_state.result = ingest_paths(
                    [path],
                    copybook_path=copybook if path.suffix.lower() in {".dat", ".ebc", ".bin"} else None,
                    persist=False,
                )

    st.markdown("---")
    st.caption("Default retrieval is TF-IDF on this machine (no model download). Set `LEGACY_INGESTOR_EMBEDDINGS=sbert` if you later install sentence-transformers.")
    st.caption(f"Portfolio demo for Daniel McBrearty · {COMPANY}")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Unstructured Legacy Ingestor")
st.caption(
    "Turn messy scans, mainframe extracts, and spreadsheets into a searchable store, with a citation back to the source. "
    "A portfolio demo — not a production migration tool."
)
st.markdown(
    f'<div class="demo-banner">'
    f"<strong>Honest label:</strong> this is a demo for interviews and practice, running on "
    f"<em>sample files</em> for {escape(COMPANY)}, a fictional mid-size dealer group. "
    "It does not connect to a real DMS, and it does not send data to a paid API. "
    "OCR will misread a character now and then — that is the point of the quality report. "
    "This is not production software."
    "</div>",
    unsafe_allow_html=True,
)

# Default: ingest bundled samples once.
if st.session_state.result is None:
    if any(SAMPLES_DIR.rglob("*")):
        st.session_state.result = _ingest_cached()
    else:
        st.warning("No sample files yet. Run `python -m ingestor generate` and reload.")
        st.stop()

result = st.session_state.result
report = result.report

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Files processed", f"{report.files_processed}")
m2.metric("Records parsed", f"{report.records_parsed}")
m3.metric("Rejected", f"{report.records_rejected}")
m4.metric("Flagged for review", f"{report.records_for_review}")
m5.metric("Chunks indexed", f"{report.chunks_indexed}")

if report.notes:
    for note in report.notes:
        st.caption(note)

tab_search, tab_pipeline, tab_quality = st.tabs(["Search with citations", "Pipeline", "Quality report"])

# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
with tab_search:
    st.markdown(
        "Ask about a customer, a VIN, a claim, or a repair order. "
        "Every hit cites the source file, and the page or record it came from."
    )
    query = st.text_input("Search", key="query", label_visibility="collapsed")
    run = st.button("Search", type="primary")
    if (run or not st.session_state.auto_searched) and result.store is not None:
        st.session_state.hits = result.store.search(st.session_state.query, k=6)
        st.session_state.auto_searched = True
    if st.session_state.hits is not None:
        _render_hits(st.session_state.hits)

# ---------------------------------------------------------------------------
# Pipeline: raw -> extracted -> cleaned -> chunks
# ---------------------------------------------------------------------------
with tab_pipeline:
    st.markdown("Walk one source from the raw file, through extraction and cleaning, to the chunks that get indexed.")
    records = result.records
    if not records and not result.previews:
        st.info("Nothing was ingested.")
    else:
        file_names = []
        for preview in result.previews:
            if preview.name not in file_names:
                file_names.append(preview.name)
        for record in records:
            if record.source_file not in file_names:
                file_names.append(record.source_file)
        selected = st.selectbox("Source file", file_names, key="pipeline_source")
        preview = next((p for p in result.previews if p.name == selected), None)
        file_records = [r for r in records if r.source_file == selected]

        raw_col, img_col = st.columns((3, 2) if preview and preview.image_path else (1, 0))
        with raw_col:
            st.subheader("Raw")
            if preview:
                st.caption(f"Detected as **{preview.source_type}**.")
                st.markdown(f'<div class="raw-box">{escape(preview.raw_preview)}</div>', unsafe_allow_html=True)
            else:
                st.caption("No raw preview for this file.")
        if preview and preview.image_path and Path(preview.image_path).is_file():
            with img_col:
                st.subheader("Scan")
                st.image(preview.image_path, use_container_width=True)

        st.subheader("Extracted and cleaned")
        if not file_records:
            st.info("No records were produced for this file.")
        else:
            labels = [_record_label(r) for r in file_records]
            pick = st.selectbox("Record", labels, key=f"rec_{selected}")
            record = file_records[labels.index(pick)]
            st.markdown(
                f'<span class="cite-pill {_status_class(record.status)}">{escape(record.status)}</span>',
                unsafe_allow_html=True,
            )
            if record.ocr_confidence is not None:
                st.caption(f"OCR confidence: {record.ocr_confidence:.0f}%")
            if record.reject_reason:
                st.error(record.reject_reason)
            if record.flags:
                st.warning(" · ".join(record.flags))
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Extracted (raw text)**")
                st.markdown(
                    f'<div class="raw-box">{escape(record.raw_text or "(empty)")}</div>',
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown("**Cleaned fields**")
                if record.fields:
                    st.json(record.fields, expanded=True)
                else:
                    st.caption("No structured fields.")
                st.markdown("**Cleaned text**")
                st.markdown(
                    f'<div class="raw-box">{escape(record.cleaned_text or "(empty)")}</div>',
                    unsafe_allow_html=True,
                )

        st.subheader("Chunks")
        file_chunks = [c for c in result.chunks if c.source_file == selected]
        if not file_chunks:
            st.caption("No chunks (rejected records are not indexed).")
        else:
            for chunk in file_chunks:
                st.markdown(
                    f'<div class="chunk-card">'
                    f'<div class="chunk-kicker">{escape(chunk.citation())}</div>'
                    f"<div>{escape(chunk.text)}</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )

# ---------------------------------------------------------------------------
# Quality report
# ---------------------------------------------------------------------------
with tab_quality:
    st.markdown(
        "A week-one data conversation starts here: what parsed, what was rejected, "
        "and what a person should look at before anyone trusts a model over this corpus."
    )
    if report.by_source_type:
        st.caption(
            "Parsed by type: "
            + ", ".join(f"{k} {v}" for k, v in sorted(report.by_source_type.items()))
        )
    r1, r2 = st.columns(2)
    with r1:
        st.subheader("Rejects")
        if report.rejects:
            st.dataframe(report.rejects, use_container_width=True, hide_index=True)
        else:
            st.caption("No rejects.")
    with r2:
        st.subheader("Flagged for human review")
        if report.review_items:
            st.dataframe(report.review_items, use_container_width=True, hide_index=True)
        else:
            st.caption("Nothing flagged for review.")
    st.subheader("Field-level issues")
    if report.field_issues:
        st.dataframe(report.field_issues, use_container_width=True, hide_index=True)
    else:
        st.caption("No field-level issues were recorded.")
