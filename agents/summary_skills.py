"""Agent 2 — Summary + Skills (merged).

Generates the professional summary AND the 3-category skills section
in a single call.  Auto-picks the best summary from 3 candidates.
"""

from .base import call_agent_json, master_resume_cache_block

SYSTEM = """\
You are a resume optimization specialist.  Given a JD analysis and master resume,
produce BOTH the professional summary AND the skills section in one response.

## PART 1: PROFESSIONAL SUMMARY

Generate 3 candidate summaries ranked best to worst, then select the best one.

### Summary rules
- Maximum 340 characters INCLUDING spaces
- ASCII-only punctuation. No em dashes — use commas or "with" connectors
- No banned buzzwords: passionate, driven, seasoned, dynamic, results-oriented,
  self-starter, guru, ninja, rockstar, synergy
- No first-person pronouns (I, my, me, myself)
- No content that duplicates resume bullets
- Mirror 2-3 key terms from the JD naturally
- Lead with an identity noun matching the role
- Use "N years" or "N+ years" (honest count)

### 6-second-scan rules
- First ~170 chars must surface evidence for the JD's most-gating Basic Quals
- Identity noun must match JD's exact role title
- Maximum 1 buzz word per summary

### Year computation
Sum months across qualifying PM/relevant experiences, divide by 12:
- Matic: started 2026-01 to present
- Saayam: 2025-02 to 2025-12 = 10 months
- Wurq: 2023-09 to 2024-01 = 4 months
- ZS: 2021-06 to 2022-06 = 12 months
Round honestly.

## PART 2: SKILLS SECTION

Build the optimal 3-category skills section.

### Sourcing logic (priority order)
1. JD-extracted — anything literally named in the JD
2. Master_resume-backed — every final skill must trace to master_resume content
3. Master-resume-only skills — include only if it strengthens the narrative

### Default PM/APM categories
1. **Product & Data** — methodologies + analytical methods
2. **Tools** — software tools and apps
3. **Technologies** — languages, frameworks, infrastructure

### SWE role category override (use these instead when role_type is SWE)
1. **Languages** — programming languages. Rust MUST always be included. If C++ appears anywhere in the JD requirements, C++ MUST also be included.
2. **Frameworks & Libraries** — frameworks, libraries, SDKs
3. **Tools & Infrastructure** — dev tools, CI/CD, cloud, databases, infrastructure

### Format constraints
- Total: 12-15 skills across all 3 categories
- 150-char max per line including "Category Name: "

### Critical rule
Every Basic-Qual keyword from the keyword inventory MUST appear in the skills section.

## Output schema (strict JSON)

```json
{
  "summary": {
    "candidates": [
      {"rank": 1, "text": "<summary>", "char_count": 320},
      {"rank": 2, "text": "<summary>", "char_count": 315},
      {"rank": 3, "text": "<summary>", "char_count": 330}
    ],
    "selected": "<text of rank 1 summary>",
    "selected_char_count": 320
  },
  "skills": {
    "skills": [
      {"name": "Product & Data", "list": "skill1, skill2, ...", "char_count": 142, "skills_count": 6},
      {"name": "Tools", "list": "skill1, ...", "char_count": 89, "skills_count": 4},
      {"name": "Technologies", "list": "skill1, ...", "char_count": 135, "skills_count": 5}
    ],
    "total_skills": 15,
    "basic_keyword_coverage": {"keyword": true}
  }
}
```

Return ONLY valid JSON.
"""


def write_summary_and_skills(
    jd_analysis: dict,
    master_resume: dict,
    role_type: str,
    fix_instructions: list[dict] | None = None,
) -> dict:
    """Generate summary and skills in one call. Returns merged result.

    Args:
        fix_instructions: Optional list of critical fixes from the coverage checker.
            Each has 'issue' and 'fix' keys. When provided, the agent is told
            exactly what keywords/skills to add.
    """
    import json

    user_msg = (
        f"## Role Type: {role_type}\n\n"
        f"## JD Analysis\n\n```json\n{json.dumps(jd_analysis, indent=2)}\n```\n\n"
    )

    if fix_instructions:
        user_msg += "## CRITICAL FIXES REQUIRED FROM PREVIOUS ROUND\n\n"
        user_msg += "The coverage checker found these problems. You MUST fix them:\n\n"
        for fix in fix_instructions:
            user_msg += f"- **{fix.get('issue', '')}** → {fix.get('fix', '')}\n"
        user_msg += (
            "\nInclude the EXACT keywords listed above in the skills section. "
            "Do not paraphrase them — use the literal terms. "
            "For example, if it says add 'API Design', write 'API Design' not 'REST APIs'. "
            "If it says add 'Unit Testing', write 'Unit Testing' not 'Testing'. "
            "If it says add 'Large Language Models', write 'Large Language Models' or 'LLMs'. "
            "If it says add 'AI Agents', write 'AI Agents'.\n\n"
        )

    user_msg += (
        "Generate 3 summary candidates (pick the best) AND the 3-category skills section. "
        "Use the master resume from your system prompt as the source of truth."
    )

    return call_agent_json(
        system=SYSTEM,
        user_message=user_msg,
        cached_system=master_resume_cache_block(master_resume),
    )
