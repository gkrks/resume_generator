-- Run this in Supabase SQL Editor (Dashboard > SQL Editor > New Query)
-- Adds evaluation check columns to resume_queue

ALTER TABLE resume_queue
  ADD COLUMN IF NOT EXISTS ats_check       boolean DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS recruiter_check boolean DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS hr_check        boolean DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS strong_apply    boolean DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS tier            text    DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS generated_at    timestamptz DEFAULT NULL;

-- tier values: 'Strong', 'Maybe', 'DontWasteTime'
-- strong_apply = true when all 3 checks pass
-- generated_at = timestamp when resume was generated

COMMENT ON COLUMN resume_queue.ats_check IS 'ATS keyword double-presence all pass';
COMMENT ON COLUMN resume_queue.recruiter_check IS 'Recruiter 6-second scan pass (title match + basic quals in top 1/3)';
COMMENT ON COLUMN resume_queue.hr_check IS 'Hiring manager deep read pass (metrics plausible + scope match + technical depth)';
COMMENT ON COLUMN resume_queue.strong_apply IS 'All 3 checks pass = true';
COMMENT ON COLUMN resume_queue.tier IS 'Strong / Maybe / DontWasteTime';
COMMENT ON COLUMN resume_queue.generated_at IS 'When the resume was generated';
