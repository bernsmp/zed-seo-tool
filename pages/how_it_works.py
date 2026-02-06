import streamlit as st

st.markdown("""
<div class="page-hero" style="border-left-color: #2D398E; background: linear-gradient(135deg, #E8EAF6 0%, #D5DAF0 100%);">
    <span class="step-badge" style="background: #2D398E;">Reference Guide</span>
    <h1>How It Works</h1>
    <p>A plain-English guide to this tool — no SEO jargon required. Start here if you're new.</p>
</div>
""", unsafe_allow_html=True)

st.divider()

# ── Quick overview ───────────────────────────────────────────────

st.subheader("What is this?")
st.markdown("""
A 4-step workflow that takes a competitor's keywords and turns them into an **action plan**
for your client: which pages to optimize, which new pages to create, and writer-ready
content briefs for each one.
""")

st.subheader("Why we built it")
st.markdown("""
SEMRush gives you raw data — thousands of keywords in a spreadsheet. The hard part is
deciding which ones matter for *your specific client* and what to actually do with them.
That manual filtering and mapping takes hours. **This tool automates it** with AI that
knows your client's business.
""")

st.subheader("How it's different from SEMRush")
st.markdown("""
**SEMRush = data collection. This tool = data decision-making.**

| SEMRush | This Tool |
|---------|-----------|
| Pulls keyword lists | Classifies which keywords are relevant to YOUR client |
| Shows what competitors rank for | Maps each keyword to a specific page on your client's site |
| Raw spreadsheets | Action plan: optimize this page, create that page, write this blog |
| No content guidance | Generates full content briefs a writer can execute |

SEMRush is the input. This tool is the output.
""")

st.subheader("How to get started")
st.markdown("""
1. **Client Setup** — Enter the client's domain, crawl their site, generate an AI profile
2. **Keyword Cleaning** — Pull competitor keywords from SEMRush (built in) → AI sorts into Keep/Remove/Unsure
3. **Keyword Mapping** — AI assigns each keyword to an existing URL or flags it as "needs a new page"
4. **Content Briefs** — AI generates detailed, writer-ready briefs for every new page needed

Start at Step 1, the tool guides you through the rest.
""")

st.divider()

# ── What this tool does ──────────────────────────────────────────

st.subheader("What does this tool do?")
st.markdown("""
When someone searches Google for something like *"best dentist near me"* or *"how to fix a leaky faucet"*,
those searches are called **keywords**. Businesses want to show up when people search for things related
to what they offer.

This tool helps you figure out three things:

1. **Which keywords actually matter** for a specific business (and which ones to ignore)
2. **Where those keywords should live** on the business's website
3. **What new content to create** — with detailed briefs ready for a writer
""")

st.divider()

# ── The steps ────────────────────────────────────────────────────

st.subheader("The Workflow")

col1, col2 = st.columns(2)

with col1:
    st.markdown("#### Step 1: Client Setup")
    st.markdown("""
    **What you do:** Enter the client's website address and click "Crawl Site."

    **What happens:** The tool scans their website and builds a profile — what services
    they offer, where they're located, what they specialize in.

    **Why it matters:** This profile is the "brain" that helps the tool make smart decisions
    in the next steps. Think of it like briefing a new employee on what the company does.

    **You can edit everything** the tool generates. Add competitor names, irrelevant locations,
    or other terms you want filtered out.
    """)

with col2:
    st.markdown("#### Step 2: Keyword Cleaning")
    st.markdown("""
    **What you do:** Pull keywords directly from SEMRush using the built-in API, or upload a CSV file from any tool.

    **What happens:** The tool reads every keyword and sorts it into three buckets:

    - **Keep** — directly relevant to the client
    - **Remove** — wrong location, wrong specialty, competitor names, too vague
    - **Unsure** — might be relevant, needs a human to decide

    **You review the results** and can move keywords between buckets before exporting.
    """)

col3, col4 = st.columns(2)

with col3:
    st.markdown("#### Step 3: Keyword Mapping")
    st.markdown("""
    **What you do:** Upload the cleaned keywords from Step 2.

    **What happens:** The tool looks at every keyword and asks: *"Does the client already
    have a page that should rank for this?"* If yes, it assigns the keyword to that page.
    If not, it flags it as a gap.

    **What you get:** A spreadsheet that tells you:

    - **Existing URL** keywords → these pages need optimization (update the page title,
      headings, and content to target these keywords)
    - **New Page** keywords → the client is missing pages for these high-value searches.
      Create dedicated service or landing pages.
    - **Blog Post** keywords → people are asking questions the client can answer. Write
      articles to capture this traffic.

    **Why this is valuable:** Instead of guessing which keyword goes where, you have a
    clear plan. Your SEO team knows exactly which pages to optimize, your content team
    knows exactly what to write, and nothing falls through the cracks.
    """)

with col4:
    st.markdown("#### Step 4: Content Briefs")
    st.markdown("""
    **What you do:** Click "Generate Briefs" for the keywords that need new content.

    **What happens:** The tool groups related keywords together and creates a detailed
    content brief for each new page or blog post — including a suggested title, outline,
    target audience, internal linking recommendations, and SEO requirements.

    **What you get:** Ready-to-hand-off briefs that a writer can execute without
    back-and-forth. Each brief includes:

    - Who the article is for and what problem it solves
    - A suggested H2 outline with section descriptions
    - Which keywords to target and where
    - Specific internal pages to link to
    - A recommended word count and tone

    **Why this is valuable:** You skip the 1-2 hours of manual brief creation per article.
    The AI already knows the client's services, existing pages, and keyword data — so the
    briefs are specific, not generic templates.
    """)

st.divider()

# ── Glossary ─────────────────────────────────────────────────────

st.subheader("Glossary — Common Terms Explained")

glossary = {
    "Keyword": "A word or phrase people type into Google. Example: *\"emergency plumber Austin TX\"*",
    "Search Volume": "How many people search for that keyword per month. Higher = more potential traffic.",
    "Keyword Difficulty (KD)": "A score (0–100) showing how hard it is to rank on page 1 for that keyword. Higher = harder.",
    "Search Intent": "**Why** someone is searching. Are they looking to buy something (transactional), learn something (informational), or find a specific website (navigational)?",
    "Keyword Gap": "Keywords your competitors rank for that you don't. It's a list of opportunities you're missing.",
    "Keyword Mapping": "Assigning each keyword to a specific page on a website. This tells your team exactly which page to optimize for which search term — so effort is focused, not scattered.",
    "Content Brief": "A document that gives a writer everything they need to create a page or article — the target keyword, audience, outline, tone, and SEO requirements. Good briefs eliminate back-and-forth.",
    "SEO (Search Engine Optimization)": "The practice of improving a website so it shows up higher in Google search results.",
    "AEO (Answer Engine Optimization)": "Optimizing content so AI assistants (like ChatGPT, Google AI Overviews) use your content as an answer source.",
    "SERP": "Search Engine Results Page — the page you see after you Google something.",
    "Crawling": "When a tool (or Google) scans a website to understand what's on each page.",
    "Sitemap": "A file on a website that lists all its pages — like a table of contents for search engines.",
    "On-Page Optimization": "Updating a specific page's title, headings, content, and meta tags to better target a keyword. This is what you do with the 'Existing URL' results from keyword mapping.",
    "Content Gap": "A keyword or topic that people search for but the client has no page covering it. Filling content gaps is one of the fastest ways to grow organic traffic.",
}

for term, definition in glossary.items():
    with st.expander(f"**{term}**"):
        st.markdown(definition)

st.divider()

# ── FAQ ──────────────────────────────────────────────────────────

st.subheader("Frequently Asked Questions")

with st.expander("Where do I get the keyword data?"):
    st.markdown("""
    **Recommended:** Use the built-in SEMRush API integration on the Keyword Cleaning page.
    Just enter your domain and competitor domains, and the tool pulls keywords directly —
    no CSV export needed.

    **Alternatively, upload a CSV** from SEO tools like:
    - **SEMRush** — use the "Keyword Gap" report, export as CSV
    - **Ahrefs** — use the "Content Gap" tool, export as CSV
    - **Google Search Console** — export your queries

    The CSV needs at minimum a column called "Keyword." Columns for Volume,
    Keyword Difficulty, and Intent are helpful but optional.
    """)

with st.expander("How much does it cost to run?"):
    st.markdown("""
    This tool uses AI to classify keywords. Each run costs a small amount based on
    how many keywords you process. The tool shows you an **estimate before you start**
    so there are no surprises.

    Typical costs:
    - 500 keywords: ~$0.10 – $0.25
    - 2,000 keywords: ~$0.50 – $1.00
    """)

with st.expander("What if the tool classifies a keyword wrong?"):
    st.markdown("""
    That's expected! The tool gets it right most of the time, but the **review step exists
    for exactly this reason**. You can change any keyword's classification before exporting.
    The "Unsure" bucket catches edge cases so you can make the final call.
    """)

with st.expander("Do I need to crawl the site every time?"):
    st.markdown("""
    No. Once you set up a client profile, it's saved. You only need to re-crawl if the
    client's website changes significantly (new pages, new services, etc.).
    """)

with st.expander("What's the difference between Keyword Cleaning and Keyword Mapping?"):
    st.markdown("""
    **Cleaning** = filtering. You start with a big messy list and remove the junk.

    **Mapping** = organizing. You take the good keywords and assign each one to a page.

    Think of it like sorting mail: Cleaning is throwing away the spam. Mapping is putting
    each letter in the right mailbox.
    """)

with st.expander("Why can't I just do this in SEMRush?"):
    st.markdown("""
    SEMRush is excellent at **pulling data** — keyword lists, competitor analysis, rankings.
    But it gives you raw data and leaves the strategy to you.

    This tool picks up where SEMRush stops:
    - SEMRush gives you 5,000 keywords → this tool tells you which 200 actually matter for *your client*
    - SEMRush shows competitor keywords → this tool assigns each keyword to a specific page on *your client's* site
    - SEMRush has a basic content template → this tool generates detailed briefs using *your client's* profile, URL inventory, and keyword strategy

    **SEMRush provides the data** — and with the built-in API integration, you can pull it directly without leaving this tool. Then the AI turns that data into an action plan.
    """)
