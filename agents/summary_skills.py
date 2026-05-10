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
Round up to the nearest whole year.

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
1. **Languages** — programming languages only. Rust MUST always be included. If C++ appears anywhere in the JD requirements, C++ MUST also be included.
2. **Frameworks & Libraries** — frameworks, libraries, SDKs only
3. **Tools & Infrastructure** — concrete, nameable tools and platforms only.
   Examples of what BELONGS here: CI/CD, GitHub Actions, AWS Lambda, Docker,
   PostgreSQL, Kafka, Terraform, Kubernetes, metrics dashboards, coding agents.
   Examples of what DOES NOT belong here: "developer tooling", "infrastructure",
   "internal platforms", "developer experience", "engineering productivity",
   "workflow automation", "AI-driven development", "systems design",
   "end-to-end ownership", "monorepo tooling". These are job responsibilities
   or domain descriptions, NOT tools. Never list them as skills.

### Format constraints
- 5-6 skills per category. No more than 6 in any single category.
- Total: 15-18 skills across all 3 categories. HARD CAP at 18.
- 150-char max per line including "Category Name: "
- If a line exceeds 150 chars or a category exceeds 6 skills, cut the
  least important skill. Do not overflow.

### Keyword coverage rule
Try to cover Basic-Qual keywords from the JD in the skills section, but ONLY
if they are actual tools, languages, frameworks, or concrete technologies.

ABSOLUTE BAN LIST — these are NOT skills and must NEVER appear in the skills
section, even if the JD lists them as requirements or fix instructions ask
for them:
- "developer tooling", "developer experience", "infrastructure",
  "internal platforms", "engineering productivity", "workflow automation",
  "AI-driven development", "systems design", "end-to-end ownership",
  "monorepo tooling", "monorepo", "codebase context", "cloud dev environments",
  "coding agents", "automated refactors", "metrics and dashboards"
These are job responsibilities or domain concepts. They go in the summary
or bullets, NEVER in the skills section.

If fix instructions from a previous round ask you to add any banned term
to skills, IGNORE that fix instruction. The 18-skill hard cap and the ban
list override all fix instructions.

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
      {"name": "Product & Data", "list": "skill1, skill2, ...", "char_count": 142, "skills_count": 5},
      {"name": "Tools", "list": "skill1, ...", "char_count": 89, "skills_count": 5},
      {"name": "Technologies", "list": "skill1, ...", "char_count": 135, "skills_count": 5}
    ],
    "total_skills": 15,  // 15-18 max, HARD CAP at 18
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
    previous_output: dict | None = None,
) -> dict:
    """Generate summary and skills in one call. Returns merged result.

    Args:
        fix_instructions: Critical fixes from the coverage checker.
        previous_output: The full output from the previous round that PASSED checks.
            When provided, the agent preserves everything that worked and only
            modifies what the fix instructions specify.
    """
    import json

    user_msg = (
        f"## Role Type: {role_type}\n\n"
        f"## JD Analysis\n\n```json\n{json.dumps(jd_analysis, indent=2)}\n```\n\n"
    )

    if previous_output and fix_instructions:
        user_msg += "## PREVIOUS ROUND OUTPUT (PRESERVE WHAT WORKS)\n\n"
        user_msg += (
            "The following summary and skills were generated in the previous round. "
            "Most of this output PASSED the coverage checker. **Keep everything that "
            "was working. Only modify or add what the fix instructions below specify.** "
            "Do NOT remove skills or change the summary unless a fix explicitly asks for it.\n\n"
        )
        user_msg += f"```json\n{json.dumps(previous_output, indent=2)}\n```\n\n"

        user_msg += "## CRITICAL FIXES REQUIRED\n\n"
        user_msg += "Fix ONLY these specific issues while preserving everything else:\n\n"
        for fix in fix_instructions:
            user_msg += f"- **{fix.get('issue', '')}** → {fix.get('fix', '')}\n"
        user_msg += (
            "\nInclude the EXACT keywords listed above in the skills section. "
            "Do not paraphrase — use the literal terms. "
            "Do NOT remove any skills that were already present.\n\n"
        )
    elif fix_instructions:
        user_msg += "## CRITICAL FIXES REQUIRED FROM PREVIOUS ROUND\n\n"
        user_msg += "The coverage checker found these problems. You MUST fix them:\n\n"
        for fix in fix_instructions:
            user_msg += f"- **{fix.get('issue', '')}** → {fix.get('fix', '')}\n"
        user_msg += (
            "\nInclude the EXACT keywords listed above in the skills section. "
            "Do not paraphrase them — use the literal terms.\n\n"
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
