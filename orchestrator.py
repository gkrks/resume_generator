"""Orchestrator — chains all agents and generates the full application package.

Optimized pipeline (4 calls, prompt-cached, parallel where possible):

  1. JD Analyzer          (Sonnet, cached master_resume)
  2. Summary + Skills     (Sonnet, cached master_resume)  ← merged
  3. Bullet Matcher       (Sonnet, cached master_resume)
  4. Coverage Checker     (Sonnet)
     -> Fix loop if CRITICAL (up to 2 rounds)
  5. Cover Letter + Outreach  (Haiku)  ← merged, runs in parallel with file gen

Output path:
  ~/Desktop/Resumes/{Strong|Maybe|DontWasteTime}/{CompanyName}/{JobRole}/{date}/
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from agents.jd_analyzer import analyze_jd
from agents.summary_skills import write_summary_and_skills
from agents.bullet_matcher import match_bullets
from agents.coverage_checker import check_coverage
from agents.cover_outreach import write_cover_and_outreach
from generators.resume_json import build_working_resume, save_working_resume
from generators.cover_letter_js import generate_cover_letter_js
from generators.file_writer import write_outreach as write_outreach_file
from generators.report_pdf import generate_report_pdf

MAX_FIX_LOOPS = 2
PROJECT_ROOT = Path(__file__).resolve().parent
RESUMES_ROOT = Path(os.environ.get(
    "RESUMES_OUTPUT_DIR",
    "/Users/rashmicagopinath/Desktop/Resumes",
))


def _log(step: str, msg: str):
    print(f"\n{'='*60}")
    print(f"  [{step}] {msg}")
    print(f"{'='*60}\n")


def _sanitize(name: str) -> str:
    name = re.sub(r"[^\w\s\-]", "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name or "Unknown"


def _compute_checks(coverage_result: dict) -> dict:
    """Extract ATS / Recruiter / HR pass booleans from coverage checker output."""
    dp = coverage_result.get("coverage_report", {}).get("basic_keyword_double_presence", [])
    ats_check = all(k.get("status", "").upper() == "PASS" for k in dp) if dp else True

    re_eval = coverage_result.get("recruiter_eval", {})
    title_pass = re_eval.get("title_match", {}).get("status", "").upper() == "PASS"
    bq = re_eval.get("basic_qual_top_third", {})
    bq_pass = bq.get("covered", 0) == bq.get("total", 1)
    recruiter_check = title_pass and bq_pass

    hm_eval = coverage_result.get("hm_eval", {})
    metrics_pass = all(
        m.get("status", "").upper() == "PASS"
        for m in hm_eval.get("metric_plausibility", [])
    )
    scope_pass = hm_eval.get("scope_seniority", {}).get("status", "").upper() == "PASS"
    tech_pass = hm_eval.get("technical_depth", {}).get("status", "").upper() == "PASS"
    hr_check = metrics_pass and scope_pass and tech_pass

    passes = sum([ats_check, recruiter_check, hr_check])
    strong_apply = passes == 3
    if passes == 3:
        tier = "Strong"
    elif passes == 2:
        tier = "Maybe"
    else:
        tier = "DontWasteTime"

    return {
        "ats_check": ats_check,
        "recruiter_check": recruiter_check,
        "hr_check": hr_check,
        "strong_apply": strong_apply,
        "tier": tier,
    }


def _enforce_keyword_coverage(jd_analysis: dict, skills_data: dict) -> dict:
    """Log missing Basic-Qual keywords but do NOT inject them.

    Previously this force-injected every missing keyword into the last
    skills category, causing keyword stuffing. Now it only logs what's
    missing so the coverage checker can evaluate naturally.
    """
    inventory = jd_analysis.get("keyword_inventory", [])
    required_keywords = [
        k["keyword"] for k in inventory
        if k.get("embed_target", "").lower() == "required"
    ]

    if not required_keywords:
        return skills_data

    skills_lines = skills_data.get("skills", [])
    all_skills_text = " | ".join(s.get("list", "") for s in skills_lines).lower()

    missing = [kw for kw in required_keywords if kw.lower() not in all_skills_text]

    if missing:
        print(f"  [keyword-coverage] Keywords not in skills (OK if abstract): {missing}")

    return skills_data


def _build_folder_parts(role_type: str, tier: str, company: str, role_title: str) -> list[str]:
    """Build the folder path parts for both local and Drive."""
    return [
        role_type.upper(),
        date.today().strftime("%-d %b"),  # "9 May"
        tier,
        _sanitize(company),
        _sanitize(role_title),
    ]


def _build_output_dir(folder_parts: list[str]) -> Path:
    """Build local output dir from folder parts."""
    out = RESUMES_ROOT
    for part in folder_parts:
        out = out / part
    out.mkdir(parents=True, exist_ok=True)
    return out


def _generate_resume_files(
    master_resume, jd_analysis, summary, skills_data, bullet_result,
    out_dir, company_safe, tmp_dir,
):
    """Generate resume PDF (runs in thread pool)."""
    working_resume = build_working_resume(
        master_resume, jd_analysis, summary, skills_data, bullet_result
    )
    working_json_path = str(tmp_dir / f"working_resume_{company_safe}.json")
    save_working_resume(working_resume, working_json_path)

    resume_basename = f"Resume_Krithik_Gopinath_{company_safe}"
    fill_cmd = [
        "node", str(PROJECT_ROOT / "fill_resume.js"),
        "--input", working_json_path,
        "--out-basename", resume_basename,
    ]
    result = subprocess.run(fill_cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print(f"  fill_resume.js FAILED:\n{result.stderr}")

    resume_pdf_src = PROJECT_ROOT / "out" / (resume_basename + ".pdf")
    resume_pdf_dst = out_dir / (resume_basename + ".pdf")
    if resume_pdf_src.exists():
        shutil.copy2(str(resume_pdf_src), str(resume_pdf_dst))

    return str(resume_pdf_dst)


def _generate_cover_letter_files(
    company, role, cl_result, out_dir, company_safe, tmp_dir,
):
    """Generate cover letter DOCX (runs in thread pool)."""
    cl_data = cl_result.get("cover_letter", {})
    cl_js = generate_cover_letter_js(
        company=company,
        role=role,
        para1=cl_data.get("paragraph_1", ""),
        para2=cl_data.get("paragraph_2", ""),
        output_dir=str(out_dir),
        filmsearch_invite=cl_data.get("filmsearch_invite", ""),
    )
    cl_js_path = str(tmp_dir / f"cover_letter_{company_safe}.js")
    with open(cl_js_path, "w") as f:
        f.write(cl_js)

    env = os.environ.copy()
    env["NODE_PATH"] = str(PROJECT_ROOT / "node_modules")
    cl_run = subprocess.run(
        ["node", cl_js_path], capture_output=True, text=True, cwd=str(PROJECT_ROOT), env=env,
    )
    if cl_run.returncode != 0:
        print(f"  Cover letter JS FAILED:\n{cl_run.stderr}")

    # Remove the PDF, keep only DOCX
    cl_basename = f"Cover_Letter_Krithik_Gopinath_{company_safe}"
    cl_pdf = out_dir / (cl_basename + ".pdf")
    if cl_pdf.exists():
        cl_pdf.unlink()

    return str(out_dir / (cl_basename + ".docx"))


def run(
    jd_text: str,
    role_type: str = "PM",
    output_base: str | None = None,
    job_id: str | None = None,
    job_meta: dict | None = None,
) -> dict:
    """Run the full multi-agent pipeline.

    Optimized: 4 API calls (down from 7), prompt-cached, parallel file gen.
    """
    master_path = PROJECT_ROOT / "config" / "master_resume.json"
    with open(master_path) as f:
        master_resume = json.load(f)

    # For SWE roles, swap bullets with swe_bullets so all agents see
    # engineering-framed bullets without needing prompt-level changes.
    if role_type.upper() == "SWE":
        for section in ("experiences", "projects"):
            for item in master_resume.get(section, []):
                if "swe_bullets" in item:
                    item["bullets"] = item.pop("swe_bullets")
                else:
                    item.pop("swe_bullets", None)

    tmp_dir = Path(tempfile.mkdtemp(prefix="resume_gen_"))

    # ── Step 1: JD Analysis (Sonnet, cached) ─────────────────────
    _log("1/5", "Analyzing job description...")
    jd_analysis = analyze_jd(jd_text, master_resume, role_type)
    company = jd_analysis.get("company", "Unknown")
    role = jd_analysis.get("role_title", role_type)
    company_safe = _sanitize(company)
    role_safe = _sanitize(role)

    _log("1/5", f"Company: {company} | Role: {role} | "
         f"Layout: {jd_analysis.get('layout')} | "
         f"Reqs: {len(jd_analysis.get('requirements', []))} | "
         f"Keywords: {len(jd_analysis.get('keyword_inventory', []))}")

    # ── Step 2: Summary + Skills (Sonnet, cached, merged) ────────
    _log("2/5", "Writing summary + skills...")
    merged = write_summary_and_skills(jd_analysis, master_resume, role_type)
    summary_data = merged.get("summary", {})
    skills_data = merged.get("skills", {})
    summary = summary_data.get("selected", "")
    _log("2/5", f"Summary ({summary_data.get('selected_char_count', len(summary))} chars): {summary[:80]}...")

    # Enforce: inject any missing Basic-Qual keywords into the skills section
    skills_data = _enforce_keyword_coverage(jd_analysis, skills_data)

    for s in skills_data.get("skills", []):
        _log("2/5", f"  {s['name']}: {s['list'][:60]}... ({s.get('char_count', '?')} chars)")

    # ── Step 3: Bullet Matching (Sonnet, cached) ─────────────────
    _log("3/5", "Batch-matching and rewriting bullets...")
    bullet_result = match_bullets(jd_analysis, skills_data, master_resume)
    tracker = bullet_result.get("allocation_tracker", {})
    total = tracker.get("total", {})
    _log("3/5", f"Bullets locked: {total.get('locked', '?')}/{total.get('allocated', '?')}")

    # ── Step 4: Coverage Check (with early exit + stateful fix loop) ──
    _log("4/5", "Running coverage check + self-evaluation...")
    for fix_round in range(MAX_FIX_LOOPS + 1):
        coverage_result = check_coverage(jd_analysis, summary, skills_data, bullet_result)
        verdict = coverage_result.get("verdict", "PROCEED")
        _log("4/5", f"Round {fix_round}: Verdict = {verdict}")

        if verdict == "PROCEED" or fix_round == MAX_FIX_LOOPS:
            break

        critical_fixes = coverage_result.get("critical_fixes", [])
        _log("4/5", f"CRITICAL fixes needed: {len(critical_fixes)}")
        for fix in critical_fixes:
            _log("4/5", f"  - {fix.get('issue', '')[:80]}")

        # Early exit: if all 3 checks fail on round 0, the gap is genuine
        # — fix loops won't help, skip them to save 2 API calls per agent
        if fix_round == 0:
            checks_preview = _compute_checks(coverage_result)
            if not any([checks_preview["ats_check"], checks_preview["recruiter_check"],
                        checks_preview["hr_check"]]):
                _log("4/5", "Early exit: all 3 checks failed on round 0 — gap is genuine, skipping fix loops")
                break

        # Re-run with fix instructions AND previous good state
        if any(f.get("target_step") in ("skills", "bullets", "summary") for f in critical_fixes):
            previous_merged = {"summary": summary_data, "skills": skills_data}
            previous_bullets = bullet_result.get("final_bullets", {})

            merged = write_summary_and_skills(
                jd_analysis, master_resume, role_type,
                fix_instructions=critical_fixes,
                previous_output=previous_merged,
            )
            skills_data = merged.get("skills", {})
            skills_data = _enforce_keyword_coverage(jd_analysis, skills_data)
            summary_data = merged.get("summary", {})
            summary = summary_data.get("selected", "")

            bullet_result = match_bullets(
                jd_analysis, skills_data, master_resume,
                fix_instructions=critical_fixes,
                previous_bullets=previous_bullets,
            )

    # Compute checks and tier
    checks = _compute_checks(coverage_result)
    tier = checks["tier"]
    _log("4/5", f"ATS: {'PASS' if checks['ats_check'] else 'FAIL'} | "
         f"Recruiter: {'PASS' if checks['recruiter_check'] else 'FAIL'} | "
         f"HR: {'PASS' if checks['hr_check'] else 'FAIL'} | Tier: {tier}")

    # Set up output directory based on tier
    folder_parts = _build_folder_parts(role_type, tier, company, role)
    if output_base:
        out_dir = Path(output_base)
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = _build_output_dir(folder_parts)
    _log("4/5", f"Output: {out_dir}")

    # ── Step 5: Cover Letter + Outreach + File Gen (parallel) ────
    _log("5/5", "Generating all files in parallel...")

    with ThreadPoolExecutor(max_workers=3) as pool:
        # Thread 1: Cover letter + outreach (Haiku API call)
        cl_future = pool.submit(write_cover_and_outreach, jd_analysis, summary, bullet_result)

        # Thread 2: Resume PDF generation (node fill_resume.js)
        resume_future = pool.submit(
            _generate_resume_files,
            master_resume, jd_analysis, summary, skills_data, bullet_result,
            out_dir, company_safe, tmp_dir,
        )

        # Thread 3: Evaluation report PDF (local, no API call)
        report_pdf_path = str(out_dir / f"Evaluation_Report_{company_safe}_{role_safe}.pdf")
        report_future = pool.submit(
            generate_report_pdf, coverage_result, jd_analysis, report_pdf_path, job_meta,
        )

        # Wait for cover letter + outreach result, then generate files
        cl_result = cl_future.result()
        resume_pdf_path = resume_future.result()
        report_future.result()

    # Generate cover letter DOCX from the CL result
    cl_docx_path = _generate_cover_letter_files(
        company, role, cl_result, out_dir, company_safe, tmp_dir,
    )

    # Write outreach markdown
    outreach = cl_result.get("outreach", {})
    outreach_path = str(out_dir / f"Cold_Outreach_{company_safe}.md")
    write_outreach_file(outreach, outreach_path)

    # Cleanup
    shutil.rmtree(str(tmp_dir), ignore_errors=True)

    # ── Done ─────────────────────────────────────────────────────
    generated = {
        "output_dir": str(out_dir),
        "tier": tier,
        "folder_parts": folder_parts,
        "resume_pdf": resume_pdf_path,
        "evaluation_report": report_pdf_path,
        "cover_letter_docx": cl_docx_path,
        "cold_outreach": outreach_path,
        "checks": checks,
    }

    _log("DONE", f"[{tier}] All files written to {out_dir}")
    print("\nGenerated files:")
    for k, v in generated.items():
        if isinstance(v, str) and os.path.exists(v):
            print(f"  {k}: {v}")
    print(f"\n  Tier: {tier} | ATS: {checks['ats_check']} | "
          f"Recruiter: {checks['recruiter_check']} | HR: {checks['hr_check']}")

    return generated
