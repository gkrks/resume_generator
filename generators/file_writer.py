"""File output helpers — writes all artifacts to the output directory."""

import json
import os


def write_coverage_report(coverage_result: dict, output_path: str) -> str:
    """Write the coverage report as markdown."""
    lines = ["# COVERAGE REPORT\n"]

    # Requirement coverage
    lines.append("## Requirement Coverage\n")
    lines.append("| Req # | Requirement | Type | Status | Coverage |")
    lines.append("|-------|-------------|------|--------|----------|")
    for r in coverage_result.get("coverage_report", {}).get("requirement_coverage", []):
        lines.append(
            f"| {r.get('req_id', '')} | {r.get('requirement', '')[:60]} | "
            f"{r.get('type', '')} | {r.get('status', '')} | {r.get('coverage', '')} |"
        )

    # Skills coverage
    lines.append("\n## Skills Coverage\n")
    lines.append("| Skill | Where it appears | Gap? |")
    lines.append("|-------|------------------|------|")
    for s in coverage_result.get("coverage_report", {}).get("skills_coverage", []):
        where = ", ".join(s.get("where", []))
        gap = "YES" if s.get("gap") else ""
        lines.append(f"| {s.get('skill', '')} | {where} | {gap} |")

    # Basic keyword double-presence
    lines.append("\n## Basic-Qual Keyword Double-Presence\n")
    lines.append("| Keyword | In Skills | In Bullet | Status |")
    lines.append("|---------|-----------|-----------|--------|")
    for k in coverage_result.get("coverage_report", {}).get("basic_keyword_double_presence", []):
        in_s = "Y" if k.get("in_skills") else "N"
        in_b = "Y" if k.get("in_bullet") else "N"
        lines.append(f"| {k.get('keyword', '')} | {in_s} | {in_b} | {k.get('status', '')} |")

    # Verdict
    lines.append(f"\n## Verdict: {coverage_result.get('verdict', 'UNKNOWN')}\n")
    for fix in coverage_result.get("critical_fixes", []):
        lines.append(f"- **{fix.get('issue', '')}** -> {fix.get('fix', '')} (target: {fix.get('target_step', '')})")

    content = "\n".join(lines)
    with open(output_path, "w") as f:
        f.write(content)
    return output_path


def write_self_eval(coverage_result: dict, output_path: str) -> str:
    """Write the recruiter + HM self-evaluation as markdown."""
    lines = ["# SELF-EVALUATION REPORT\n"]

    # Recruiter
    re = coverage_result.get("recruiter_eval", {})
    lines.append("## Recruiter Persona Findings\n")
    tm = re.get("title_match", {})
    lines.append(f"- Title match: **{tm.get('status', '')}** - {tm.get('detail', '')}")
    bq = re.get("basic_qual_top_third", {})
    lines.append(f"- Basic Qual top-1/3 coverage: {bq.get('covered', 0)}/{bq.get('total', 0)} covered")
    for g in bq.get("gaps", []):
        lines.append(f"  - GAP: {g}")
    lines.append("- Keyword double-presence:")
    for k in re.get("keyword_double_presence", []):
        in_s = "Y" if k.get("in_skills") else "N"
        in_b = "Y" if k.get("in_bullets") else "N"
        lines.append(f"  - {k.get('keyword', '')}: Skills={in_s}, Bullets={in_b} -> {k.get('status', '')}")
    lines.append("- Top 3 reject reasons:")
    for r in re.get("top_3_reject_reasons", []):
        lines.append(f"  - {r}")

    # Hiring Manager
    hm = coverage_result.get("hm_eval", {})
    lines.append("\n## Hiring Manager Persona Findings\n")
    lines.append("- Metric plausibility:")
    for m in hm.get("metric_plausibility", []):
        lines.append(f"  - {m.get('bullet', '')[:60]}: {m.get('status', '')} {m.get('note', '')}")
    ss = hm.get("scope_seniority", {})
    lines.append(f"- Scope-seniority: **{ss.get('status', '')}** - {ss.get('detail', '')}")
    td = hm.get("technical_depth", {})
    lines.append(f"- Technical depth: **{td.get('status', '')}** - {td.get('detail', '')}")
    lines.append("- Day-1 readiness:")
    for d in hm.get("day1_readiness", []):
        lines.append(f"  - {d.get('responsibility', '')[:50]}: {d.get('status', '')} ({d.get('proof_bullet', '')})")

    content = "\n".join(lines)
    with open(output_path, "w") as f:
        f.write(content)
    return output_path


def write_outreach(outreach_result: dict, output_path: str) -> str:
    """Write cold outreach templates as markdown."""
    lines = ["# COLD OUTREACH TEMPLATES\n"]

    ce = outreach_result.get("cold_email", {})
    lines.append("## Alumni Cold Email\n")
    lines.append(f"**Subject:** {ce.get('subject', '')}\n")
    lines.append(f"**Body:**\n\n{ce.get('body', '')}\n")

    dm = outreach_result.get("linkedin_dm", {})
    lines.append("## LinkedIn DM\n")
    lines.append(f"**Body:**\n\n{dm.get('body', '')}\n")
    lines.append(f"**Footer:**\n\n{dm.get('footer', '')}\n")

    content = "\n".join(lines)
    with open(output_path, "w") as f:
        f.write(content)
    return output_path


def write_cover_letter_text(cover_letter_result: dict, output_path: str) -> str:
    """Write cover letter text as markdown (before JS generation)."""
    lines = ["# COVER LETTER\n"]
    lines.append(f"**Company research:** {cover_letter_result.get('company_research', cover_letter_result.get('company_detail', ''))}\n")
    lines.append(f"**Word count:** {cover_letter_result.get('word_count', '')}\n")
    lines.append("---\n")
    lines.append(cover_letter_result.get("paragraph_1", ""))
    para2 = cover_letter_result.get("paragraph_2", "")
    if para2:
        lines.append("")
        lines.append(para2)
    invite = cover_letter_result.get("filmsearch_invite", "")
    if invite:
        lines.append("")
        lines.append(invite)

    content = "\n".join(lines)
    with open(output_path, "w") as f:
        f.write(content)
    return output_path
