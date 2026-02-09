-- Migration: Consolidate Google Drive links into pdf_url
-- Date: 2026-02-09
-- Purpose: Simplify schema by using single pdf_url field for all PDF sources

-- Step 1: Move existing Google Drive links to pdf_url (if pdf_url is NULL)
UPDATE jobs 
SET pdf_url = gdrive_link 
WHERE gdrive_link IS NOT NULL 
  AND pdf_url IS NULL;

-- Step 2: Handle edge case where both exist (prefer gdrive_link)
UPDATE jobs 
SET pdf_url = gdrive_link 
WHERE gdrive_link IS NOT NULL 
  AND pdf_url IS NOT NULL;

-- Step 3: Drop the gdrive_link column
ALTER TABLE jobs 
DROP COLUMN IF EXISTS gdrive_link;

-- Step 4: Add comment explaining pdf_url usage
COMMENT ON COLUMN jobs.pdf_url IS 'PDF URL - can be organization PDF URL or Google Drive shareable link (uploaded FreeJobAlert PDFs)';

-- Verification queries (run separately to check):
-- SELECT COUNT(*) FROM jobs WHERE pdf_url LIKE '%drive.google.com%';
-- SELECT COUNT(*) FROM jobs WHERE pdf_url NOT LIKE '%drive.google.com%' AND pdf_url IS NOT NULL;
