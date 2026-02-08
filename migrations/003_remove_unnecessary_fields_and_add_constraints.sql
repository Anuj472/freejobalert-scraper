-- Migration: Remove unnecessary URL fields and add FreeJobAlert link blocking constraints
-- Date: 2026-02-08
-- Author: Anuj Kumar Mishra

-- STEP 1: Remove unnecessary columns
-- Remove organization_url (duplicate of official_website)
ALTER TABLE jobs DROP COLUMN IF EXISTS organization_url;

-- Remove application_url (not needed, only official_website is sufficient)
ALTER TABLE jobs DROP COLUMN IF EXISTS application_url;

-- STEP 2: Add CHECK constraints to block FreeJobAlert links
-- This ensures NO FreeJobAlert links can be saved at database level

-- Constraint for pdf_url: Must NOT contain freejobalert.com
ALTER TABLE jobs 
ADD CONSTRAINT check_no_fja_pdf_url 
CHECK (
    pdf_url IS NULL OR 
    (pdf_url NOT ILIKE '%freejobalert.com%' AND pdf_url NOT ILIKE '%www.freejobalert.com%')
);

-- Constraint for official_website: Must NOT contain freejobalert.com
ALTER TABLE jobs 
ADD CONSTRAINT check_no_fja_official_website 
CHECK (
    official_website IS NULL OR 
    (official_website NOT ILIKE '%freejobalert.com%' AND official_website NOT ILIKE '%www.freejobalert.com%')
);

-- STEP 3: Clean existing data (set to NULL if contains FreeJobAlert links)
UPDATE jobs 
SET pdf_url = NULL 
WHERE pdf_url ILIKE '%freejobalert.com%';

UPDATE jobs 
SET official_website = NULL 
WHERE official_website ILIKE '%freejobalert.com%';

-- STEP 4: Add comments to document the constraints
COMMENT ON CONSTRAINT check_no_fja_pdf_url ON jobs IS 
'Prevents FreeJobAlert links from being saved in pdf_url field. Only official organization PDFs are allowed.';

COMMENT ON CONSTRAINT check_no_fja_official_website ON jobs IS 
'Prevents FreeJobAlert links from being saved in official_website field. Only official organization websites are allowed.';

-- Verification queries (run these to verify migration)
-- SELECT COUNT(*) FROM jobs WHERE pdf_url ILIKE '%freejobalert.com%'; -- Should return 0
-- SELECT COUNT(*) FROM jobs WHERE official_website ILIKE '%freejobalert.com%'; -- Should return 0
