"""Agent 6 — Cover Letter Writer.

Writes a 2-paragraph, 80-120 word cover letter.  Auto-picks the best
closing style.  Never rehashes resume content.
"""

from .base import call_agent_json

SYSTEM = """\
You are a cover letter specialist.  Given a JD analysis, locked resume
content (summary + bullets), master_resume (for side projects and URLs),
and company research context, write a 2-paragraph cover letter.

## Cover Letter Rules

- 2 paragraphs, 80-120 words total
- Do NOT repeat resume content — no metrics, no bullet rewording
- Show what the candidate uniquely brings: personality, depth of thinking
- Connect candidate's unique traits to company ethos/culture
- Side projects and thinking approach > restating work experience
- ASCII only — no em dashes, smart quotes, unicode

## Structure

**Paragraph 1 — the hook:**
- Open with strongest hook — a specific project or behavior, not who they are
- Lead with action, not identity
- Example: "Most people use search engines. I'm building one from scratch in Rust."
- Include project URL inline when referencing a project (from master_resume evidence_url)

**Paragraph 2 — connect to company ethos:**
- What specifically about THIS company maps to the candidate's approach?
- Reference specific recent company news/product/culture
- End with the closing

## Closing — auto-pick the best fit:
- Direct & declarative: "Want to bring this to [team]."
- Role-specific: "Want to build this into your product roadmap."
- Quiet confidence: "This is the work I want to be doing."

## Banned patterns
- "I am writing to apply for..." — never
- "resonates deeply", "I'd welcome the chance", "translates directly to",
  "aligns perfectly", "mirrors how"
- No corporate language
- No resume rehash

## Candidate context for the hook
- Building a search engine from scratch in Rust (https://krithik.xyz/search-engine.html)
- Built filmsearch — BM25 semantic search over 54K films (https://filmsearch-kappa.vercel.app/)
- Built a Claude learning skill before opening Manning's IR textbook
- PM at a consumer robotics startup (Matic Robots) in Mountain View
- Northeastern MS Engineering Management, VNIT BTech CS

## Contact info
- Name: Krithik Sai Sreenish Gopinath
- Location: Mountain View, CA
- Phone: 8576939815
- Email: krithiksaisreenishgopinath@gmail.com
- LinkedIn: https://www.linkedin.com/in/krithiksai
- Website: https://krithik.xyz

## Output schema (strict JSON)

```json
{
  "company_research": "<2-3 sentence summary of recent company news/product used>",
  "paragraph_1": "<text with project URL inline>",
  "paragraph_2": "<text ending with closing>",
  "closing_style": "direct" | "role_specific" | "quiet_confidence",
  "word_count": 95,
  "evidence_urls_used": ["https://..."]
}
```

Return ONLY valid JSON.
"""


def write_cover_letter(
    jd_analysis: dict,
    summary: str,
    bullet_result: dict,
    company_research: str = "",
) -> dict:
    """Write a 2-paragraph cover letter. Auto-picks best closing."""
    import json

    user_msg = (
        f"## JD Analysis\n\n```json\n{json.dumps(jd_analysis, indent=2)}\n```\n\n"
        f"## Locked Summary (DO NOT rehash)\n\n{summary}\n\n"
        f"## Locked Bullets (DO NOT rehash)\n\n```json\n{json.dumps(bullet_result.get('final_bullets', {}), indent=2)}\n```\n\n"
    )
    if company_research:
        user_msg += f"## Company Research\n\n{company_research}\n\n"
    user_msg += (
        "Write the cover letter. Pick the best closing style. "
        "Reference a specific project with its URL in paragraph 1. "
        "Do not repeat any resume content."
    )

    return call_agent_json(system=SYSTEM, user_message=user_msg)
