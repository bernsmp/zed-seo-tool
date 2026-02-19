"""
CWV Audit — Core Web Vitals & CLS diagnosis tool.
Paste a URL (or batch list), get real-user field data vs. lab scores,
CLS element breakdown, and WordPress-aware fix recommendations.
"""

import os
import time

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env.local"))
load_dotenv()

# ── Constants ─────────────────────────────────────────────────────

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

# CLS thresholds (Google's official)
CLS_GOOD = 0.1
CLS_NEEDS_IMPROVEMENT = 0.25

# Performance score thresholds
PERF_GOOD = 0.9
PERF_NEEDS_IMPROVEMENT = 0.5

# LCP thresholds (ms)
LCP_GOOD = 2500
LCP_NEEDS_IMPROVEMENT = 4000

# WordPress-aware CLS diagnosis rules.
# Each rule: (label, selector_patterns, cause, fix_snippet)
WP_PATTERNS = [
    (
        "Revolution Slider",
        [".rev_slider", ".tp-", ".revslider", "rev_slider_wrapper"],
        "Revolution Slider renders at 0px height then expands — classic CLS trigger. "
        "The wrapper has no reserved height before the slider JS initialises.",
        ".rev_slider_wrapper {\n    min-height: 400px; /* match your slider height */\n}",
    ),
    (
        "Images Without Dimensions",
        ["img", "wp-post-image", "attachment-", "size-"],
        "Image has no explicit width/height attributes. Browser can't reserve space, "
        "so content shifts when the image loads.",
        "/* Option 1 — add to functions.php (WordPress auto-adds dimensions) */\nadd_filter('wp_lazy_loading_enabled', '__return_false');\n\n"
        "/* Option 2 — CSS fix for images inside content */\n.entry-content img {\n    aspect-ratio: attr(width) / attr(height);\n    height: auto;\n    width: 100%;\n}",
    ),
    (
        "Navigation / Header",
        ["header", "nav", "x-navbar", "site-header", "masthead", "x-header", "cs-header"],
        "Header or nav has no explicit height. When sticky behaviour kicks in or fonts "
        "load, the header resizes and shifts all content below it.",
        ".site-header,\n.x-navbar,\nheader[role='banner'] {\n    min-height: 80px; /* match your header height */\n    contain: layout;\n}",
    ),
    (
        "Cornerstone / X Theme Layout",
        [".x-", ".cornerstone", ".cs-", "x-section", "x-row", "x-column"],
        "Cornerstone uses percentage-based column widths without explicit heights. "
        "Content reflows as sibling elements load, especially above the fold.",
        "/* Add to Cornerstone > Global CSS */\n.x-section:first-of-type .x-row {\n    contain: layout size;\n}\n.x-column > .x-content-band {\n    min-height: 1px; /* prevents zero-height collapse */\n}",
    ),
    (
        "Gravity Forms",
        ["gform_wrapper", "gfield", "ginput", "gform-"],
        "Gravity Forms renders a container then injects field markup via JS, "
        "causing the surrounding content to shift down.",
        ".gform_wrapper {\n    min-height: 300px; /* approximate form height */\n    contain: layout;\n}",
    ),
    (
        "Web Font Swap (FOUT)",
        ["font-face", "google-font", "fonts.gstatic", "fonts.googleapis"],
        "Web fonts load asynchronously. When the font swaps in, text reflows because "
        "the fallback font has different metrics — a very common CLS source.",
        "/* Add to your <style> or Customizer > Additional CSS */\n@font-face {\n    font-display: optional; /* prevents FOUT entirely — no swap */\n    /* or use 'swap' + size-adjust if you need the font guaranteed */\n}\n\n/* If using Google Fonts link, add &display=optional to the URL */",
    ),
    (
        "Cookie Banner / Consent Modal",
        ["cookie", "consent", "gdpr", "cookiebot", "cookie-notice"],
        "Cookie banner inserts at the top of the page after initial render, "
        "pushing all content down. This is one of the most common CLS sources.",
        "/* Force the banner to overlay instead of push content */\n.cookie-notice-container,\n#cookie-law-info-bar,\n.cookiebot-banner {\n    position: fixed !important;\n    bottom: 0;\n    top: auto !important;\n    z-index: 9999;\n}",
    ),
    (
        "UberMenu / Navigation Plugin",
        ["ubermenu", "uber-menu", "ub-menu"],
        "UberMenu loads its styles asynchronously and can shift the header "
        "height on render, especially on first load or cache miss.",
        "/* Reserve nav height in the header before UberMenu loads */\n.ubermenu-main {\n    min-height: 50px;\n    contain: layout;\n}",
    ),
]


# ── Helper functions ───────────────────────────────────────────────

def _cls_color(score: float) -> str:
    if score <= CLS_GOOD:
        return "#00a550"
    if score <= CLS_NEEDS_IMPROVEMENT:
        return "#ff9800"
    return "#e53935"


def _perf_color(score: float) -> str:
    if score >= PERF_GOOD:
        return "#00a550"
    if score >= PERF_NEEDS_IMPROVEMENT:
        return "#ff9800"
    return "#e53935"


def _lcp_color(ms: int) -> str:
    if ms <= LCP_GOOD:
        return "#00a550"
    if ms <= LCP_NEEDS_IMPROVEMENT:
        return "#ff9800"
    return "#e53935"


def _field_category_color(cat: str) -> str:
    return {"FAST": "#00a550", "AVERAGE": "#ff9800", "SLOW": "#e53935"}.get(cat, "#888")


def _diagnose_element(selector: str, node_label: str) -> tuple[str, str, str] | None:
    """Match an element against WP patterns. Returns (pattern_name, cause, fix) or None."""
    combined = (selector + " " + node_label).lower()
    for name, patterns, cause, fix in WP_PATTERNS:
        if any(p.lower() in combined for p in patterns):
            return name, cause, fix
    return None


def _run_psi(url: str, strategy: str = "mobile") -> dict:
    """Call PageSpeed Insights API and return the JSON response."""
    api_key = os.getenv("PAGESPEED_API_KEY", "")
    params = {"url": url, "strategy": strategy, "locale": "en"}
    if api_key:
        params["key"] = api_key
    resp = requests.get(PSI_ENDPOINT, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _extract_metrics(data: dict) -> dict:
    """Pull the key numbers out of a PSI response."""
    lhr = data.get("lighthouseResult", {})
    audits = lhr.get("audits", {})
    cats = lhr.get("categories", {})
    field = data.get("loadingExperience", {})
    origin_field = data.get("originLoadingExperience", {})

    def audit_val(key):
        a = audits.get(key, {})
        return a.get("numericValue"), a.get("displayValue"), a.get("score"), a.get("details", {})

    cls_val, cls_display, cls_score, cls_details = audit_val("cumulative-layout-shift")
    lcp_val, lcp_display, lcp_score, _ = audit_val("largest-contentful-paint")
    tbt_val, tbt_display, tbt_score, _ = audit_val("total-blocking-time")
    fcp_val, fcp_display, fcp_score, _ = audit_val("first-contentful-paint")
    si_val, si_display, si_score, _ = audit_val("speed-index")

    # CLS shifting elements
    shifting_items = cls_details.get("items", [])

    # Field data (CrUX)
    field_metrics = field.get("metrics", {})
    field_cls = field_metrics.get("CUMULATIVE_LAYOUT_SHIFT_SCORE", {})
    field_lcp = field_metrics.get("LARGEST_CONTENTFUL_PAINT_MS", {})
    field_overall = field.get("overall_category", "")

    # Origin-level field data
    origin_metrics = origin_field.get("metrics", {})
    origin_cls = origin_metrics.get("CUMULATIVE_LAYOUT_SHIFT_SCORE", {})
    origin_overall = origin_field.get("overall_category", "")

    perf_score = cats.get("performance", {}).get("score", 0)

    return {
        "perf_score": perf_score,
        "cls_val": float(cls_val or 0) ,
        "cls_display": cls_display or "N/A",
        "cls_score": cls_score,
        "lcp_val": int(lcp_val or 0),
        "lcp_display": lcp_display or "N/A",
        "tbt_val": int(tbt_val or 0),
        "tbt_display": tbt_display or "N/A",
        "fcp_display": fcp_display or "N/A",
        "si_display": si_display or "N/A",
        "shifting_items": shifting_items,
        "field_cls_percentile": field_cls.get("percentile", None),
        "field_cls_category": field_cls.get("category", ""),
        "field_lcp_percentile": field_lcp.get("percentile", None),
        "field_overall": field_overall,
        "origin_cls_percentile": origin_cls.get("percentile", None),
        "origin_cls_category": origin_cls.get("category", ""),
        "origin_overall": origin_overall,
        "url": data.get("id", ""),
    }


# ── Page ───────────────────────────────────────────────────────────

st.markdown("""
<div class="page-hero">
    <span class="step-badge">SEO Tools</span>
    <h1>Core Web Vitals Audit</h1>
    <p>Real-user field data vs. lab scores. CLS element diagnosis. WordPress-aware fix recommendations.</p>
</div>
""", unsafe_allow_html=True)

# ── Expert framing callout ─────────────────────────────────────────

st.markdown("""
<div class="info-callout">
    <strong>Two layers on every finding:</strong>
    &nbsp;<span style="background:#1B2B5E;color:#E8F0FE;padding:2px 8px;border-radius:4px;font-size:0.78rem;font-weight:600;">DEFAULT</span>
    &nbsp;What any report shows you.&ensp;
    <span style="background:#266BA2;color:#E8F0FE;padding:2px 8px;border-radius:4px;font-size:0.78rem;font-weight:600;">EXPERT</span>
    &nbsp;What changes when you apply WordPress-specific domain knowledge — named cause + copy-paste fix.
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ── Tabs: Single URL vs Batch ─────────────────────────────────────

tab_single, tab_batch = st.tabs(["Single URL", "Batch URLs"])

# ── SINGLE URL TAB ────────────────────────────────────────────────

with tab_single:
    col_url, col_strat = st.columns([4, 1])
    with col_url:
        single_url = st.text_input(
            "URL to audit",
            placeholder="https://westtxent.com/conditions/sinus-infection-nasal-obstruction/",
            key="cwv_single_url",
        )
    with col_strat:
        strategy = st.selectbox("Device", ["mobile", "desktop"], key="cwv_strategy")

    run_single = st.button("Run Audit", type="primary", key="cwv_run_single")

    if run_single and single_url:
        if not single_url.startswith("http"):
            st.error("Please include the full URL with https://")
        else:
            with st.spinner("Calling PageSpeed Insights API…"):
                try:
                    raw = _run_psi(single_url.strip(), strategy)
                    m = _extract_metrics(raw)
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 429:
                        st.error("Rate limit hit (429) — the unauthenticated PSI API allows ~25 requests/day.")
                        st.markdown("""
**Fix: get a free API key (2 min)**
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. APIs & Services → Enable APIs → search **PageSpeed Insights API** → Enable
3. APIs & Services → Credentials → Create Credentials → API Key
4. Add to `.env.local`: `PAGESPEED_API_KEY=AIza...`
5. Restart the app

Free tier gives **25,000 requests/day**.
""")
                    else:
                        st.error(f"API error: {e.response.status_code} — {e.response.text[:300]}")
                    st.stop()
                except Exception as e:
                    st.error(f"Error: {e}")
                    st.stop()

            # ── Score cards ───────────────────────────────────────
            st.markdown("### Overall Scores")
            c1, c2, c3, c4, c5, c6 = st.columns(6)

            perf_pct = int(m["perf_score"] * 100)
            c1.metric("Performance", f"{perf_pct}/100")
            c2.metric("CLS", m["cls_display"])
            c3.metric("LCP", m["lcp_display"])
            c4.metric("TBT", m["tbt_display"])
            c5.metric("FCP", m["fcp_display"])
            c6.metric("Speed Index", m["si_display"])

            # ── Field vs Lab ───────────────────────────────────────
            st.markdown("### Field Data vs Lab Data")

            has_field = m["field_cls_percentile"] is not None
            has_origin = m["origin_cls_percentile"] is not None

            if has_field or has_origin:
                fl_col, lab_col = st.columns(2)

                with fl_col:
                    st.markdown("**Real-User Data (CrUX) — what Google Search Console reports**")

                    if has_field:
                        page_cls = m["field_cls_percentile"] / 100
                        page_cat = m["field_cls_category"]
                        cat_color = _field_category_color(page_cat)
                        st.markdown(
                            f"**This page CLS (p75):** "
                            f"<span style='color:{cat_color};font-weight:700'>{page_cls:.2f} — {page_cat}</span>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown("*Page-level CrUX data not available (not enough traffic)*")

                    if has_origin:
                        origin_cls = m["origin_cls_percentile"] / 100
                        origin_cat = m["origin_cls_category"]
                        cat_color2 = _field_category_color(origin_cat)
                        st.markdown(
                            f"**Whole-site CLS (p75):** "
                            f"<span style='color:{cat_color2};font-weight:700'>{origin_cls:.2f} — {origin_cat}</span>",
                            unsafe_allow_html=True,
                        )

                with lab_col:
                    st.markdown("**Lab Data (Lighthouse) — single simulated load**")
                    lab_cls = m["cls_val"]
                    lab_color = _cls_color(lab_cls)
                    st.markdown(
                        f"**Lab CLS:** <span style='color:{lab_color};font-weight:700'>{lab_cls:.3f}</span>",
                        unsafe_allow_html=True,
                    )

                # Gap alert
                if has_field:
                    page_cls_val = m["field_cls_percentile"] / 100
                    gap = abs(page_cls_val - m["cls_val"])
                    if gap > 0.05:
                        st.markdown("""
<div style="background:#FFF8E1;border-left:3px solid #ff9800;border-radius:0 8px 8px 0;
     padding:0.75rem 1rem;margin:0.5rem 0;font-size:0.875rem;color:#5D4037;">
<strong>Field vs Lab gap detected (>{:.2f}).</strong>
This means real users experience worse CLS than the lab test shows. Common causes:
late-loading ads, personalised content, or cookie banners that only appear for
real users (not in Lighthouse's headless environment).
</div>""".format(gap), unsafe_allow_html=True)

                # Expert badge explanation
                st.markdown("""
<div style="display:flex;gap:1rem;margin-top:0.5rem;flex-wrap:wrap;">
  <div style="background:#1B2B5E;color:#E8F0FE;padding:4px 12px;border-radius:6px;font-size:0.78rem;font-weight:600;">
    DEFAULT: CLS = 0.12 (needs improvement)
  </div>
  <div style="background:#266BA2;color:#E8F0FE;padding:4px 12px;border-radius:6px;font-size:0.78rem;font-weight:600;">
    EXPERT: Lab shows 0.12, but real users see 0.18. The gap = cookie banner / late-loading ads not captured by headless Lighthouse.
  </div>
</div>""", unsafe_allow_html=True)

            else:
                st.info("No field data available for this URL — not enough real-user traffic in CrUX dataset.")

            # ── CLS Element Breakdown ──────────────────────────────
            st.markdown("---")
            st.markdown("### CLS Element Breakdown")

            if not m["shifting_items"]:
                st.success("No layout-shifting elements detected in this lab run. CLS issues may be user-interaction-dependent or only appear in field data.")
            else:
                for i, item in enumerate(m["shifting_items"]):
                    node = item.get("node", {})
                    selector = node.get("selector", "")
                    node_label = node.get("nodeLabel", "")
                    snippet = node.get("snippet", "")
                    shift_score = item.get("score", item.get("totalCumulativeScore", 0))

                    diagnosis = _diagnose_element(selector, node_label)

                    with st.expander(
                        f"{'🔴' if float(shift_score or 0) > 0.05 else '🟡'} "
                        f"Element {i + 1}: {selector[:60] or node_label[:60]} — shift score {float(shift_score or 0):.3f}",
                        expanded=(i == 0),
                    ):
                        # DEFAULT box
                        st.markdown("""
<div style="background:#F5F5F5;border-left:3px solid #666;border-radius:0 6px 6px 0;
     padding:0.65rem 1rem;margin-bottom:0.5rem;font-size:0.85rem;">
<span style="background:#555;color:#fff;padding:2px 7px;border-radius:4px;
font-size:0.72rem;font-weight:600;margin-right:6px;">DEFAULT</span>
<strong>Element shifted during page load.</strong><br>
""" + (f"Selector: <code>{selector}</code><br>" if selector else "") +
(f"Label: {node_label}<br>" if node_label else "") +
f"Shift score: <strong>{float(shift_score or 0):.3f}</strong></div>", unsafe_allow_html=True)

                        if snippet:
                            st.code(snippet, language="html")

                        # EXPERT box
                        if diagnosis:
                            d_name, d_cause, d_fix = diagnosis
                            st.markdown(f"""
<div style="background:#EBF5FB;border-left:3px solid #266BA2;border-radius:0 6px 6px 0;
     padding:0.75rem 1rem;margin-top:0.25rem;font-size:0.85rem;color:#1B2B5E;">
<span style="background:#266BA2;color:#E8F0FE;padding:2px 7px;border-radius:4px;
font-size:0.72rem;font-weight:600;margin-right:6px;">EXPERT</span>
<strong>Diagnosed: {d_name}</strong><br><br>
{d_cause}
</div>""", unsafe_allow_html=True)
                            st.markdown("**Recommended fix:**")
                            st.code(d_fix, language="css")
                        else:
                            st.markdown("""
<div style="background:#EBF5FB;border-left:3px solid #266BA2;border-radius:0 6px 6px 0;
     padding:0.75rem 1rem;margin-top:0.25rem;font-size:0.85rem;color:#1B2B5E;">
<span style="background:#266BA2;color:#E8F0FE;padding:2px 7px;border-radius:4px;
font-size:0.72rem;font-weight:600;margin-right:6px;">EXPERT</span>
No WordPress-specific pattern matched. Inspect this element in Chrome DevTools →
Performance tab → Layout Shift Regions (check the box) to see the exact shift moment.
</div>""", unsafe_allow_html=True)

            # ── CLS Fix Priority Guide ─────────────────────────────
            if m["cls_val"] > CLS_GOOD or (has_field and m["field_cls_percentile"] / 100 > CLS_GOOD):
                st.markdown("---")
                st.markdown("### Fix Priority Guide")

                st.markdown("""
<div style="background:#F9F9F9;border-radius:8px;padding:1rem 1.25rem;font-size:0.875rem;line-height:1.7;">
<strong>High impact, low effort (do these first):</strong><br>
1. Add <code>width</code> and <code>height</code> attributes to all <code>&lt;img&gt;</code> tags above the fold<br>
2. Add <code>min-height</code> to your header/navbar container<br>
3. Switch Google Fonts URL to <code>&amp;display=optional</code><br><br>
<strong>Medium impact, medium effort:</strong><br>
4. Set explicit height on Revolution Slider wrapper<br>
5. Pin cookie banner to <code>position: fixed; bottom: 0</code><br><br>
<strong>Needs theme/plugin access:</strong><br>
6. Cornerstone: add <code>contain: layout</code> to above-fold sections<br>
7. Gravity Forms: add <code>min-height</code> to form wrappers
</div>""", unsafe_allow_html=True)

            st.markdown("---")
            st.caption(
                f"Data source: Google PageSpeed Insights API · Strategy: {strategy} · "
                "Field data = CrUX 28-day p75 · Lab data = single Lighthouse run"
            )


# ── BATCH TAB ─────────────────────────────────────────────────────

with tab_batch:
    st.markdown("Paste one URL per line. Runs mobile audit on each and returns a summary table.")

    batch_text = st.text_area(
        "URLs (one per line)",
        height=150,
        placeholder="https://westtxent.com/\nhttps://westtxent.com/conditions/hearing-loss/\nhttps://westtxent.com/solutions/allergy-testing-treatments/",
        key="cwv_batch_urls",
    )
    batch_delay = st.slider(
        "Delay between requests (seconds)", 1, 5, 2,
        help="PSI API is rate-limited without an API key. 2s is safe for most runs.",
        key="cwv_batch_delay",
    )
    run_batch = st.button("Run Batch Audit", type="primary", key="cwv_run_batch")

    if run_batch and batch_text.strip():
        urls = [u.strip() for u in batch_text.strip().splitlines() if u.strip().startswith("http")]
        if not urls:
            st.error("No valid URLs found. Make sure each URL starts with http:// or https://")
        else:
            results = []
            progress = st.progress(0, text=f"Auditing {len(urls)} URLs…")

            for idx, url in enumerate(urls):
                progress.progress((idx) / len(urls), text=f"Auditing {url[:60]}…")
                try:
                    raw = _run_psi(url, "mobile")
                    m = _extract_metrics(raw)
                    field_cls = (
                        f"{m['field_cls_percentile'] / 100:.2f} ({m['field_cls_category']})"
                        if m["field_cls_percentile"] is not None
                        else "N/A"
                    )
                    results.append({
                        "URL": url,
                        "Perf Score": int(m["perf_score"] * 100),
                        "Lab CLS": round(m["cls_val"], 3),
                        "Field CLS (p75)": field_cls,
                        "LCP": m["lcp_display"],
                        "TBT": m["tbt_display"],
                        "Shifting Elements": len(m["shifting_items"]),
                    })
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 429:
                        st.warning("Rate limit hit (429). Add PAGESPEED_API_KEY to .env.local for 25,000 requests/day (free).")
                        break
                    results.append({
                        "URL": url,
                        "Perf Score": "ERROR",
                        "Lab CLS": f"HTTP {e.response.status_code}",
                        "Field CLS (p75)": "—",
                        "LCP": "—",
                        "TBT": "—",
                        "Shifting Elements": "—",
                    })
                except Exception as e:
                    results.append({
                        "URL": url,
                        "Perf Score": "ERROR",
                        "Lab CLS": str(e)[:60],
                        "Field CLS (p75)": "—",
                        "LCP": "—",
                        "TBT": "—",
                        "Shifting Elements": "—",
                    })

                if idx < len(urls) - 1:
                    time.sleep(batch_delay)

            progress.progress(1.0, text="Done!")

            import pandas as pd
            df = pd.DataFrame(results)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Flag worst offenders
            bad = [r for r in results if isinstance(r["Lab CLS"], float) and r["Lab CLS"] > CLS_GOOD]
            if bad:
                st.markdown(f"**{len(bad)} URL(s) need CLS attention** (Lab CLS > {CLS_GOOD}):")
                for r in sorted(bad, key=lambda x: x["Lab CLS"], reverse=True):
                    st.markdown(f"- `{r['URL']}` — CLS: **{r['Lab CLS']}**, {r['Shifting Elements']} shifting element(s)")

            st.caption("Mobile strategy · Field data = CrUX p75 · Lab data = Lighthouse · Rate-limited: use an API key for large batches")

# ── Sidebar: API key tip ───────────────────────────────────────────
with st.sidebar:
    st.divider()
    st.caption("CWV AUDIT")
    api_key_set = bool(os.getenv("PAGESPEED_API_KEY"))
    if api_key_set:
        st.success("PSI API key active")
    else:
        st.warning("No PSI API key set")
        st.caption("Add PAGESPEED_API_KEY to .env.local for higher rate limits (free from Google Cloud Console).")
