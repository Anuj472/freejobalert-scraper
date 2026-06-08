-- ============================================================
-- Migration 006: Update data_source constraint for Gemma 4
-- Run in: Supabase Dashboard → SQL Editor
-- ============================================================

-- Fix the data_source CHECK constraint to include gemma4 values
ALTER TABLE public.jobs
  DROP CONSTRAINT IF EXISTS check_data_source;

ALTER TABLE public.jobs
  ADD CONSTRAINT check_data_source CHECK (
    data_source = ANY(ARRAY[
      'pdf_gemma3'::text,
      'html_gemma3'::text,
      'pdf_gemma4'::text,
      'html_gemma4'::text,
      'html_css'::text,
      'html_only'::text
    ])
    OR data_source IS NULL
  );
