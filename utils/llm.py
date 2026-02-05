"""
LLM client — OpenRouter API via openai library.
Handles keyword classification, keyword mapping, and profile generation.
Tracks actual token usage and costs per session.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env.local"))
load_dotenv()  # Fallback to .env

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY not set. "
                "Add it to .env.local or set the environment variable."
            )
        _client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            default_headers={
                "HTTP-Referer": "http://localhost:8501",
                "X-Title": "SEO Keyword Tool",
            },
        )
    return _client


def _model() -> str:
    return os.getenv("DEFAULT_LLM_MODEL", "anthropic/claude-haiku-4-5-20251001")


# ── Pricing table ($ per 1M tokens on OpenRouter) ───────────────

MODEL_PRICING = {
    "anthropic/claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "anthropic/claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
    "google/gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "moonshotai/kimi-k2": {"input": 0.50, "output": 2.40},
}

# ── Cost tracker ─────────────────────────────────────────────────

_COST_LOG_DIR = Path(__file__).parent.parent / "data" / "cost_logs"


class CostTracker:
    """Tracks actual token usage and costs within a session."""

    def __init__(self):
        self.calls: list[dict] = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_usd = 0.0

    def record(self, model: str, input_tokens: int, output_tokens: int, task: str = ""):
        pricing = MODEL_PRICING.get(model, {"input": 1.00, "output": 5.00})
        cost = (input_tokens * pricing["input"] / 1_000_000) + (
            output_tokens * pricing["output"] / 1_000_000
        )
        entry = {
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 6),
            "task": task,
        }
        self.calls.append(entry)
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost_usd += cost

    def summary(self) -> dict:
        return {
            "total_calls": len(self.calls),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
        }

    def save_log(self, client_slug: str = "global"):
        _COST_LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _COST_LOG_DIR / f"{client_slug}_{ts}.json"
        path.write_text(json.dumps({
            "summary": self.summary(),
            "calls": self.calls,
        }, indent=2))
        return path


# Global tracker instance — lives for the Streamlit session
cost_tracker = CostTracker()


# ── Retry-wrapped LLM call ──────────────────────────────────────


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
)
def _chat(messages: list[dict], response_format: Optional[dict] = None, task: str = "") -> str:
    """Single LLM call with retry. Returns raw content string."""
    model = _model()
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
    }
    if response_format:
        kwargs["response_format"] = response_format
    resp = _get_client().chat.completions.create(**kwargs)

    # Track actual token usage from response
    usage = resp.usage
    if usage:
        cost_tracker.record(
            model=model,
            input_tokens=usage.prompt_tokens or 0,
            output_tokens=usage.completion_tokens or 0,
            task=task,
        )

    return resp.choices[0].message.content


def _parse_json(text: str) -> dict | list:
    """Parse JSON from LLM response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        # Strip markdown code block
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    return json.loads(text)


# ── JSON schemas for structured output ───────────────────────────

CLASSIFICATION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "keyword_classifications",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "classifications": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "keyword": {"type": "string"},
                            "classification": {
                                "type": "string",
                                "enum": ["KEEP", "REMOVE", "UNSURE"],
                            },
                            "reason": {"type": "string"},
                        },
                        "required": ["keyword", "classification", "reason"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["classifications"],
            "additionalProperties": False,
        },
    },
}

MAPPING_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "keyword_mappings",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "mappings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "keyword": {"type": "string"},
                            "url": {"type": "string"},
                            "confidence": {"type": "number"},
                            "intent": {"type": "string"},
                            "notes": {"type": "string"},
                        },
                        "required": [
                            "keyword",
                            "url",
                            "confidence",
                            "intent",
                            "notes",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["mappings"],
            "additionalProperties": False,
        },
    },
}


# ── Public API ───────────────────────────────────────────────────


def classify_keywords(
    profile: dict,
    keywords: list[dict],
    examples: Optional[list[dict]] = None,
) -> list[dict]:
    """Classify a batch of keywords as KEEP / REMOVE / UNSURE.

    Args:
        profile: Client profile dict.
        keywords: List of dicts with at least 'keyword' key (may include volume, kd, intent).
        examples: Optional anchor examples from prior batches for consistency.

    Returns:
        List of dicts: [{keyword, classification, reason}, ...]
    """
    keyword_lines = "\n".join(
        f"- {kw['keyword']}"
        + (f" (Volume: {kw.get('volume', 'N/A')}, KD: {kw.get('kd', 'N/A')}, Intent: {kw.get('intent', 'N/A')})" if kw.get("volume") else "")
        for kw in keywords
    )

    anchor_section = ""
    if examples:
        anchor_lines = "\n".join(
            f"- \"{ex['keyword']}\" → {ex['classification']} ({ex['reason']})"
            for ex in examples[:3]
        )
        anchor_section = f"\nANCHOR EXAMPLES (classifications from this session — use these for consistency):\n{anchor_lines}\n"

    prompt = f"""You are an SEO keyword relevance filter.

CLIENT PROFILE:
{json.dumps(profile, indent=2)}
{anchor_section}
KEYWORDS TO CLASSIFY:
{keyword_lines}

For each keyword, classify as:
- KEEP: Directly relevant to client's services, locations, or specialties
- REMOVE: Wrong location, wrong specialty, competitor name, too generic (single words with no SEO value)
- UNSURE: Potentially relevant but needs human judgment

Rules:
- Never modify keywords. Return them exactly as provided.
- Be conservative: UNSURE rather than incorrect REMOVE.
- Generic single-word terms → REMOVE
- Location terms for OTHER locations → REMOVE
- Competitor/doctor names → REMOVE"""

    raw = _chat(
        [{"role": "user", "content": prompt}],
        response_format=CLASSIFICATION_SCHEMA,
        task="classify_keywords",
    )
    data = _parse_json(raw)
    return data.get("classifications", data) if isinstance(data, dict) else data


def map_keywords(
    profile: dict,
    keywords: list[dict],
    urls: list[dict],
) -> list[dict]:
    """Map keywords to existing URLs or recommend new pages.

    Args:
        profile: Client profile dict.
        keywords: List of dicts with 'keyword' (and optionally volume/intent).
        urls: List of dicts with 'url', 'title', 'summary'.

    Returns:
        List of dicts: [{keyword, url, confidence, intent, notes}, ...]
    """
    url_lines = "\n".join(
        f"- {u['url']} | {u.get('title', '')} | {u.get('summary', '')}"
        for u in urls
    )
    keyword_lines = "\n".join(
        f"- {kw['keyword']}"
        + (f" (Volume: {kw.get('volume', 'N/A')}, Intent: {kw.get('intent', 'N/A')})" if kw.get("volume") else "")
        for kw in keywords
    )

    prompt = f"""You are an SEO keyword-to-URL mapper.

CLIENT PROFILE:
{json.dumps(profile, indent=2)}

CLIENT URLS:
{url_lines}

KEYWORDS TO MAP:
{keyword_lines}

For each keyword:
- Map to BEST existing URL if topical match exists
- "NEW_PAGE" if keyword needs a dedicated service/landing page (transactional intent)
- "BLOG_POST" if keyword is informational and no existing page covers it

Rules:
- Only map if genuine topical match (don't force-fit)
- Multiple keywords mapping to same URL is fine (keyword clustering)
- Consider search intent: transactional → service page, informational → blog"""

    raw = _chat(
        [{"role": "user", "content": prompt}],
        response_format=MAPPING_SCHEMA,
        task="map_keywords",
    )
    data = _parse_json(raw)
    return data.get("mappings", data) if isinstance(data, dict) else data


def generate_client_profile(domain: str, pages: list[dict]) -> dict:
    """Analyze crawled pages and generate a structured client profile.

    Args:
        domain: The client's domain.
        pages: List of dicts with 'url', 'title', 'content'.

    Returns:
        Dict with business_name, domain, services, locations, specialties, topics.
    """
    page_summaries = "\n\n".join(
        f"URL: {p['url']}\nTitle: {p.get('title', 'N/A')}\nContent snippet: {p.get('content', '')[:500]}"
        for p in pages[:30]
    )

    prompt = f"""Analyze these web pages from {domain} and extract a structured business profile.

PAGES:
{page_summaries}

Return a JSON object with:
- "business_name": string
- "domain": string
- "services": list of strings (services/products offered)
- "locations": list of strings (areas/cities served)
- "specialties": list of strings (specific expertise areas)
- "topics": list of strings (key content topics)

Be specific. Extract real data from the pages, don't guess."""

    raw = _chat([{"role": "user", "content": prompt}], task="generate_profile")
    return _parse_json(raw)


def estimate_cost(num_keywords: int, task_type: str = "cleaning") -> dict:
    """Estimate token usage and cost for a batch job using current model pricing.

    Token estimates based on:
    - Client profile JSON: ~800 tokens
    - 100 keywords with metadata: ~2500 tokens
    - Classification output (100 kw): ~3000 tokens (keyword + classification + reason)
    - URL inventory (50 URLs): ~3000 tokens
    - Mapping output (100 kw): ~4000 tokens (keyword + url + confidence + intent + notes)
    """
    model = _model()
    pricing = MODEL_PRICING.get(model, {"input": 1.00, "output": 5.00})

    batch_size = 100
    batches = max(1, (num_keywords + batch_size - 1) // batch_size)

    if task_type == "cleaning":
        input_per_batch = 3300  # ~800 profile + ~2500 keywords
        output_per_batch = 3000  # structured JSON classifications
    else:  # mapping
        input_per_batch = 6300  # ~800 profile + ~3000 URLs + ~2500 keywords
        output_per_batch = 4000  # structured JSON mappings

    total_input = batches * input_per_batch
    total_output = batches * output_per_batch

    cost = (total_input * pricing["input"] / 1_000_000) + (
        total_output * pricing["output"] / 1_000_000
    )

    return {
        "model": model,
        "batches": batches,
        "est_input_tokens": total_input,
        "est_output_tokens": total_output,
        "est_cost_usd": round(cost, 4),
        "est_minutes": round(batches * 0.12, 1),  # ~7s per batch for Haiku
    }
