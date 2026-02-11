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
    return os.getenv("DEFAULT_LLM_MODEL", "anthropic/claude-haiku-4.5")


# ── Pricing table ($ per 1M tokens on OpenRouter) ───────────────

MODEL_PRICING = {
    "anthropic/claude-haiku-4.5": {"input": 1.00, "output": 5.00},
    "anthropic/claude-3.5-haiku": {"input": 1.00, "output": 5.00},
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
    """Parse JSON from LLM response, handling markdown fences and extra text."""
    text = text.strip()
    # Extract content between code fences if present
    if "```" in text:
        import re
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
    # Fallback: find first { or [ and extract to matching close
    if not text.startswith(("{", "[")):
        start = min(
            (text.find(c) for c in ("{", "[") if text.find(c) >= 0),
            default=-1,
        )
        if start >= 0:
            text = text[start:]
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


def pre_filter_negatives(
    keywords: list[dict], negative_terms: list[str]
) -> tuple[list[dict], list[dict]]:
    """Split keywords into (pass_through, auto_removed) based on negative keyword matches.

    Case-insensitive substring match. Auto-removed entries get REMOVE classification
    with 100% confidence so they can merge directly into results.

    Returns:
        Tuple of (keywords to send to LLM, auto-removed results with classification data)
    """
    if not negative_terms:
        return keywords, []

    lower_terms = [t.lower() for t in negative_terms]
    pass_through = []
    auto_removed = []

    for kw in keywords:
        kw_lower = kw["keyword"].lower()
        matched_term = next((t for t in lower_terms if t in kw_lower), None)
        if matched_term:
            auto_removed.append({
                **kw,
                "classification": "REMOVE",
                "confidence": 100,
                "reason": f"Matched negative keyword: {matched_term}",
            })
        else:
            pass_through.append(kw)

    return pass_through, auto_removed


def suggest_negative_keywords(profile: dict, keywords: list[str]) -> list[dict]:
    """Analyze keywords and suggest potential negative terms based on client profile.

    Returns:
        List of dicts: [{"term": "competitor name", "reason": "Appears to be a competitor brand", "matches": 5}]
    """
    # Send a sample of unique keywords (cap at 200 to keep prompt manageable)
    unique_kws = list(dict.fromkeys(keywords))[:200]
    keyword_lines = "\n".join(f"- {kw}" for kw in unique_kws)

    existing_negatives = profile.get("negative_keywords", [])
    existing_text = ", ".join(existing_negatives) if existing_negatives else "None yet"

    prompt = f"""You are an SEO keyword analyst. Analyze this keyword list and suggest terms that should be added as negative keywords (terms to always REMOVE during cleaning).

CLIENT PROFILE:
- Business: {profile.get('business_name', 'Unknown')}
- Domain: {profile.get('domain', '')}
- Services: {', '.join(profile.get('services', [])[:10])}
- Locations: {', '.join(profile.get('locations', [])[:10])}
- Existing negative keywords: {existing_text}

KEYWORD SAMPLE ({len(unique_kws)} keywords):
{keyword_lines}

Look for these patterns:
- Competitor brand names or doctor names
- Locations the client does NOT serve
- Service categories completely unrelated to the client
- Common irrelevant modifiers (e.g. "DIY", "free", "jobs")

For each suggested term, count how many keywords in the sample contain it.
Do NOT suggest terms that are already in the existing negative keywords list.
Only suggest terms that would filter out genuinely irrelevant keywords.

Return ONLY a JSON object:
{{"suggestions": [{{"term": "competitor name", "reason": "Appears to be a competitor brand", "matches": 5}}]}}"""

    raw = _chat(
        [{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        task="suggest_negatives",
    )
    data = _parse_json(raw)
    return data.get("suggestions", []) if isinstance(data, dict) else data


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

    # Inject negative categories if present
    if profile.get("negative_categories"):
        categories_text = "\n".join(f"- {cat}" for cat in profile["negative_categories"])
        prompt += f"""
- Also REMOVE keywords matching these categories:
{categories_text}"""

    prompt += """

Return ONLY a JSON object in this exact format:
{{"classifications": [{{"keyword": "...", "classification": "KEEP|REMOVE|UNSURE", "confidence": 85, "reason": "brief explanation"}}]}}

Confidence scoring (0-100):
- 90-100: Obvious call, no ambiguity
- 70-89: Strong signal but minor doubt
- 50-69: Borderline, could go either way
- Below 50: Low confidence, flag for human review"""

    raw = _chat(
        [{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        task="classify_keywords",
    )
    data = _parse_json(raw)
    return data.get("classifications", data) if isinstance(data, dict) else data


def generate_qc_summary(profile: dict, results: list[dict]) -> dict:
    """Generate a QC summary reviewing the classification results.

    Returns dict with overall_assessment, flagged_keywords, and recommendations.
    """
    # Find the lowest-confidence and borderline classifications
    sorted_by_conf = sorted(results, key=lambda r: r.get("confidence", 50))
    bottom_5 = sorted_by_conf[:5]

    bottom_lines = "\n".join(
        f"- \"{r.get('keyword', '')}\" → {r.get('classification', '?')} "
        f"(confidence: {r.get('confidence', '?')}) — {r.get('reason', '')}"
        for r in bottom_5
    )

    keep_count = sum(1 for r in results if r.get("classification") == "KEEP")
    remove_count = sum(1 for r in results if r.get("classification") == "REMOVE")
    unsure_count = sum(1 for r in results if r.get("classification") == "UNSURE")
    avg_conf = sum(r.get("confidence", 50) for r in results) / max(len(results), 1)

    prompt = f"""You are a QC reviewer for SEO keyword classifications.

CLIENT: {profile.get('business_name', 'Unknown')} ({profile.get('domain', '')})
SERVICES: {', '.join(profile.get('services', [])[:5])}

CLASSIFICATION SUMMARY:
- Total: {len(results)} keywords
- Keep: {keep_count}, Remove: {remove_count}, Unsure: {unsure_count}
- Average confidence: {avg_conf:.0f}/100

LOWEST CONFIDENCE CLASSIFICATIONS (review these):
{bottom_lines}

Provide a brief QC assessment:
1. Are the classifications reasonable given the client profile?
2. Which specific keywords (if any) might be misclassified?
3. Any patterns you notice (e.g., too aggressive removing, too many UNSURE)?

Return ONLY a JSON object:
{{"overall_quality": "good|fair|needs_review", "score": 85, "flagged_keywords": [{{"keyword": "...", "current": "KEEP|REMOVE|UNSURE", "suggested": "KEEP|REMOVE|UNSURE", "reason": "why this might be wrong"}}], "summary": "2-3 sentence overall assessment", "tip": "one actionable suggestion"}}"""

    raw = _chat(
        [{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        task="qc_summary",
    )
    return _parse_json(raw)


def cluster_keywords(keywords: list[dict]) -> list[dict]:
    """Cluster related keywords into topic groups for content briefs.

    Args:
        keywords: List of dicts with 'keyword', 'recommendation' (New Page/Blog Post),
                  and optionally 'volume', 'search_intent', 'notes'.

    Returns:
        List of cluster dicts: [{
            "cluster_name": "short topic name",
            "content_type": "service_page" or "blog_post",
            "primary_keyword": "highest-volume keyword",
            "secondary_keywords": ["other", "related", "keywords"],
            "total_volume": 1234,
            "intent_summary": "what searchers want",
            "priority_score": 85
        }]
    """
    keyword_lines = "\n".join(
        f"- {kw['keyword']}"
        + (f" (Volume: {kw.get('volume', 'N/A')}, Intent: {kw.get('search_intent', kw.get('intent', 'N/A'))}, Type: {kw.get('recommendation', 'N/A')})" if kw.get("volume") else f" (Type: {kw.get('recommendation', 'N/A')})")
        for kw in keywords
    )

    prompt = f"""You are an SEO keyword clustering expert.

KEYWORDS TO CLUSTER:
{keyword_lines}

Group these keywords into topic clusters. Keywords in the same cluster should:
- Target the same search intent / user need
- Logically belong on the same page
- Share a common topic or theme

For each cluster:
- Pick the highest-volume keyword as the primary keyword
- List the rest as secondary keywords
- Determine content_type: "service_page" for transactional/commercial intent, "blog_post" for informational
- Calculate a priority_score (0-100) based on: total volume, business value, and competition level
- Write a brief intent_summary explaining what the searcher wants

Return ONLY a JSON object:
{{"clusters": [{{"cluster_name": "...", "content_type": "service_page|blog_post", "primary_keyword": "...", "secondary_keywords": ["..."], "total_volume": 1234, "intent_summary": "...", "priority_score": 85}}]}}"""

    raw = _chat(
        [{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        task="cluster_keywords",
    )
    data = _parse_json(raw)
    return data.get("clusters", data) if isinstance(data, dict) else data


def generate_content_brief(
    profile: dict,
    cluster: dict,
    url_inventory: list[dict],
) -> dict:
    """Generate a detailed content brief for a keyword cluster.

    Args:
        profile: Client profile dict.
        cluster: Cluster dict from cluster_keywords().
        url_inventory: Client's URL inventory for internal linking.

    Returns:
        Dict with brief sections: title, overview, audience, direction, seo, cta.
    """
    # Build URL context for internal linking
    url_lines = "\n".join(
        f"- {u['url']} | {u.get('title', '')}"
        for u in url_inventory[:30]
    )

    secondary_kws = ", ".join(cluster.get("secondary_keywords", [])[:10])
    content_type = cluster.get("content_type", "blog_post")

    type_guidance = ""
    if content_type == "service_page":
        type_guidance = """This is a SERVICE PAGE brief. The content should be:
- Conversion-focused with clear calls-to-action
- 800-1,500 words (concise, scannable)
- Structured around the service offering and client benefits
- Include trust signals (credentials, experience, results)
- Local SEO elements if location-specific"""
    else:
        type_guidance = """This is a BLOG POST brief. The content should be:
- Educational and thorough (1,500-2,500 words)
- Answer the searcher's question comprehensively
- Establish the client as a thought leader
- Include practical takeaways the reader can use
- Link naturally to relevant service pages"""

    prompt = f"""You are a senior content strategist creating a detailed content brief.

CLIENT PROFILE:
{json.dumps({k: v for k, v in profile.items() if k != "url_inventory"}, indent=2)}

KEYWORD CLUSTER:
- Primary keyword: {cluster.get("primary_keyword", "")}
- Secondary keywords: {secondary_kws}
- Search intent: {cluster.get("intent_summary", "")}
- Content type: {content_type}

CLIENT'S EXISTING PAGES (for internal linking):
{url_lines}

{type_guidance}

Create a comprehensive content brief with these sections:

1. OVERVIEW: Working title (compelling, not generic), primary keyword, content type, recommended word count, goal of this content

2. AUDIENCE: Who specifically is searching for this? What problem are they trying to solve? Where are they in the buying journey (awareness/consideration/decision)?

3. CONTENT DIRECTION:
   - Unique angle: What should make this content different from what already ranks? What can this client offer that competitors can't?
   - Outline: H2 headings with 1-2 sentence descriptions of what each section should cover
   - Questions to answer: 3-5 specific questions the content should address
   - Tone and voice guidance

4. SEO REQUIREMENTS:
   - Primary keyword placement guidance (title, H1, first paragraph, etc.)
   - Secondary keywords to weave in naturally (max 8)
   - Internal links: 3-5 specific URLs from the client's site to link to, with suggested anchor text
   - Meta title suggestion (under 60 chars)
   - Meta description suggestion (under 160 chars)

5. CTA: What should the reader do after reading? Be specific to the client's business.

Return ONLY a JSON object:
{{"title": "...", "overview": {{"working_title": "...", "primary_keyword": "...", "content_type": "...", "word_count": "1,500-2,000", "goal": "..."}}, "audience": {{"who": "...", "problem": "...", "journey_stage": "..."}}, "direction": {{"unique_angle": "...", "outline": [{{"heading": "H2 text", "description": "what to cover"}}], "questions": ["..."], "tone": "..."}}, "seo": {{"keyword_placement": "...", "secondary_keywords": ["..."], "internal_links": [{{"url": "...", "anchor_text": "..."}}], "meta_title": "...", "meta_description": "..."}}, "cta": "..."}}"""

    raw = _chat(
        [{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        task="generate_brief",
    )
    return _parse_json(raw)


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
- Consider search intent: transactional → service page, informational → blog

Return ONLY a JSON object in this exact format:
{{"mappings": [{{"keyword": "...", "url": "...|NEW_PAGE|BLOG_POST", "confidence": 0-100, "intent": "...", "notes": "..."}}]}}"""

    raw = _chat(
        [{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
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
    elif task_type == "briefs":
        input_per_batch = 4000   # ~800 profile + ~1500 URLs + ~1700 cluster context
        output_per_batch = 5000  # detailed structured brief JSON
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
