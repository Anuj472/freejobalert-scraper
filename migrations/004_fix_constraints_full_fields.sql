-- ============================================================
-- Migration 004: Fix data_source constraint + freejobalert_url NOT NULL
-- Run in: Supabase Dashboard → SQL Editor
-- ============================================================

-- STEP 1: Check for any rows with NULL freejobalert_url before enforcing NOT NULL
-- Run this first and confirm count = 0 before proceeding to STEP 2:
SELECT COUNT(*) AS null_fja_rows FROM public.jobs WHERE freejobalert_url IS NULL;

-- STEP 2: Fix the data_source CHECK constraint to include all values the scraper uses
ALTER TABLE public.jobs
  DROP CONSTRAINT IF EXISTS check_data_source;

ALTER TABLE public.jobs
  ADD CONSTRAINT check_data_source CHECK (
    data_source = ANY(ARRAY[
      'pdf_gemma3'::text,
      'html_gemma3'::text,
      'html_css'::text,
      'html_only'::text
    ])
    OR data_source IS NULL
  );

-- STEP 3: Make freejobalert_url NOT NULL (only after confirming STEP 1 count = 0)
-- If there are NULL rows, backfill them first or delete them before running this.
-- ALTER TABLE public.jobs
--   ALTER COLUMN freejobalert_url SET NOT NULL;
-- (Uncomment the two lines above once STEP 1 confirms no NULL rows)
