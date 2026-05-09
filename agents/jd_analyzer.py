"""Agent 1 — JD Analyzer.

Parses a job description, classifies every requirement, separates
buzz words from keywords, selects layout + experiences, and builds
the keyword inventory.  Auto-picks the best option at every decision point.
"""

from .base import call_agent_json, call_agent, master_resume_cache_block, MODEL_HAIKU

SYSTEM = """\
You are a resume-optimization expert.  You receive a job description (JD)
and a master_resume JSON.  Your job is to produce a structured analysis.

## Output schema (strict JSON, no commentary outside the JSON block)

```json
{
  "company": "<string>",
  "team": "<string or null>",
  "role_title": "<exact title from JD>",
  "location": "<string>",
  "yoe_range": "<e.g. 2-4>",
  "layout": "0-2" | "3+",
  "marketing_agency_variant": false,

  "requirements": [
    {
      "id": 1,
      "text": "<requirement verbatim from JD>",
      "type": "Basic" | "Preferred" | "Responsibility",
      "is_buzz_word": false
    }
  ],

  "keyword_inventory": [
    {
      "keyword": "<concrete tool/tech/methodology>",
      "source_category": "Basic" | "Preferred",
      "embed_target": "Required" | "Optional"
    }
  ],

  "selected_experiences": [
    {
      "id": "<exp id from master_resume>",
      "role_title": "<recommended title for this resume>",
      "bullets_allocated": 3
    }
  ],

  "selected_projects": [
    {
      "id": "<proj id from master_resume>",
      "bullets_allocated": 2
    }
  ],

  "title_line": "<role title from JD, centered below contact>"
}
```

## Rules

1. Extract EVERY requirement from the JD as a numbered item.
   - Basic = "Requirements", "Qualifications", "Must Have"
   - Preferred = "Preferred", "Nice to Have", "Bonus"
   - Responsibility = "Responsibilities", "What You'll Do"
   Front-load order: Basic first, then Preferred, then Responsibilities.

2. Separate buzz words (vague competency phrases) from keywords
   (concrete tools / technologies / methodologies).

3. Build keyword_inventory from Basic + Preferred only.
   embed_target = "Required" for Basic keywords, "Optional" for Preferred.

4. Layout selection:
   - 0-1 yrs only → "0-2" layout (3 exp + 2 projects = 12 bullets)
   - Anything reaching 2+ yrs → "3+" layout (4 exp + 1 project = 12 bullets)
   - **SWE override** (applies regardless of YOE): ALWAYS "swe" layout
     (4 exp + 2 projects = 12 bullets). See rule 6a.

5. Experience selection for 3+ layout (default, non-SWE):
   Matic 3, Saayam 3, Wurq 2, ZS 2, 1 project x 2 = 12 total.
   Marketing Agency variant only if JD explicitly values entrepreneurship/founder.

6. Experience selection for 0-2 layout (non-SWE):
   Matic 3, Saayam 3, Wurq 2, 2 projects x 2 = 12 total. ZS dropped.

6a. Experience & project selection for SWE layout (ALWAYS for SWE roles):
   Experiences: Matic 2, Saayam 2, Wurq 2, ZS 2 = 8 bullets.
   Projects: 2 projects x 2 bullets = 4 bullets. Total = 12.
   - Wurq MUST display as "Wurq (Harvard i-lab)" in the company name.
   - ChuckleBox MUST display as "ChuckleBox (MIT Sundai Club)" in the project name.
   - Search Engine in Rust (proj_searchengine_rust_0) is ALWAYS one of the 2 projects.
   - Second project depends on JD fit and required skills:
     * Search / NLP / information retrieval / data pipelines → filmsearch
     * Full-stack / web dev / APIs / collaborative apps → Voyantra
     * ML / audio processing / AWS / cloud infrastructure → ChuckleBox
   - If C++ appears anywhere in the JD requirements, prefer filmsearch as the second project.

7. Pick the best role title for each experience considering the JD.
   Use alternate_roles from master_resume when they better match the JD.
   **SWE role title overrides (mandatory for SWE roles):**
   - Matic → "Software Engineer (Product Associate)"
   - Saayam → "Software Engineer"
   - Wurq → "Software Developer Intern"
   - ZS → "Software Engineer"

8. Auto-pick the most impactful project(s) based on JD keyword overlap.
   For SWE roles, follow rule 6a strictly for project selection.

Return ONLY valid JSON.
"""


def analyze_jd(jd_text: str, master_resume: dict, role_type: str = "PM") -> dict:
    """Analyze a single job description against the master resume (Haiku)."""
    user_msg = (
        f"## Role Type: {role_type}\n\n"
        f"## Job Description\n\n{jd_text}\n\n"
        "Analyze this JD against the master resume in your system prompt "
        "and return the structured JSON output."
    )

    return call_agent_json(
        system=SYSTEM,
        user_message=user_msg,
        model=MODEL_HAIKU,
        cached_system=master_resume_cache_block(master_resume),
    )


BATCH_SYSTEM = SYSTEM + """

## BATCH MODE

You are analyzing MULTIPLE job descriptions in one call.
Return a JSON array — one analysis object per JD, in the same order.
Each object follows the exact same schema as single-JD mode.

```json
[
  { "company": "...", "role_title": "...", ... },
  { "company": "...", "role_title": "...", ... }
]
```

Return ONLY the JSON array.
"""


def analyze_jds_batch(
    jd_items: list[dict],
    master_resume: dict,
) -> list[dict]:
    """Analyze multiple JDs in one API call.

    Args:
        jd_items: List of {"jd_text": str, "role_type": str} dicts.
        master_resume: The full master resume.

    Returns:
        List of analysis dicts, one per JD, in the same order.
    """
    user_msg = f"Analyze these {len(jd_items)} job descriptions:\n\n"
    for i, item in enumerate(jd_items, 1):
        user_msg += f"### JD #{i} (Role Type: {item['role_type']})\n\n"
        user_msg += item["jd_text"]
        user_msg += "\n\n---\n\n"

    user_msg += f"Return a JSON array with {len(jd_items)} analysis objects, one per JD above."

    raw = call_agent(
        system=BATCH_SYSTEM,
        user_message=user_msg,
        model=MODEL_HAIKU,
        cached_system=master_resume_cache_block(master_resume),
        max_tokens=32768,
    )

    # Parse — could be a JSON array directly or in fences
    from .base import _parse_json
    import json

    raw = raw.strip()
    # Try as array first
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Extract from fences
    if "```json" in raw:
        start = raw.index("```json") + 7
        end = raw.index("```", start)
        result = json.loads(raw[start:end].strip())
        if isinstance(result, list):
            return result

    # Try finding [ ... ]
    first = raw.index("[")
    last = raw.rindex("]") + 1
    return json.loads(raw[first:last])
