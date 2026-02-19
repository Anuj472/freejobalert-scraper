-- Optional Migration: Add freejobalert_url column to track source URL
-- This allows job_url to store organization URL while still tracking FreeJobAlert source

-- Add column
ALTER TABLE public.jobs 
ADD COLUMN IF NOT EXISTS freejobalert_url TEXT;

-- Add index for faster lookups
CREATE INDEX IF NOT EXISTS idx_jobs_freejobalert_url 
ON public.jobs USING btree (freejobalert_url);

-- Add unique constraint to prevent duplicate scraping
ALTER TABLE public.jobs 
ADD CONSTRAINT jobs_freejobalert_url_unique 
UNIQUE (freejobalert_url);

-- Migrate existing data (for jobs that have FreeJobAlert URLs in job_url)
UPDATE public.jobs
SET freejobalert_url = job_url
WHERE job_url LIKE '%freejobalert.com%' 
  AND freejobalert_url IS NULL;

-- Optional: Update job_url for migrated records to use application_url if available
-- (Only run this if you want to clean up existing records)
-- UPDATE public.jobs
-- SET job_url = application_url
-- WHERE freejobalert_url IS NOT NULL 
--   AND application_url IS NOT NULL;

-- Verify
SELECT 
    COUNT(*) as total_jobs,
    COUNT(freejobalert_url) as has_fja_url,
    COUNT(application_url) as has_app_url,
    COUNT(CASE WHEN job_url LIKE '%freejobalert.com%' THEN 1 END) as fja_in_job_url
FROM public.jobs;
