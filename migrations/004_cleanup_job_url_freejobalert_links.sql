-- Migration: Clean up job_url field that incorrectly contains FreeJobAlert links
-- Date: 2026-02-08
-- Author: Anuj Kumar Mishra

-- PROBLEM:
-- job_url was being set to FreeJobAlert detail page URL instead of the "Apply Online" link
-- This happened when no "Apply Online" link was found on the page

-- SOLUTION:
-- Set job_url to NULL where it contains FreeJobAlert links
-- job_url should ONLY contain official organization application portal links
-- freejobalert_url already stores the FreeJobAlert source page for tracking

-- Clean up existing data
UPDATE jobs 
SET job_url = NULL 
WHERE job_url ILIKE '%freejobalert.com%';

-- Add CHECK constraint to prevent FreeJobAlert links in job_url
ALTER TABLE jobs 
ADD CONSTRAINT check_no_fja_job_url 
CHECK (
    job_url IS NULL OR 
    (job_url NOT ILIKE '%freejobalert.com%' AND job_url NOT ILIKE '%www.freejobalert.com%')
);

-- Add comment
COMMENT ON CONSTRAINT check_no_fja_job_url ON jobs IS 
'Ensures job_url only contains official organization application portal links (Apply Online), never FreeJobAlert links. FreeJobAlert source is stored in freejobalert_url field.';

-- Verification queries
-- SELECT COUNT(*) FROM jobs WHERE job_url ILIKE '%freejobalert.com%'; -- Should return 0
-- SELECT COUNT(*) FROM jobs WHERE job_url IS NULL; -- Shows how many jobs don't have Apply Online link
-- SELECT COUNT(*) FROM jobs WHERE freejobalert_url IS NOT NULL; -- All records should have this (source tracking)
