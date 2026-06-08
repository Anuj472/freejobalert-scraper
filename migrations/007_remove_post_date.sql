-- ============================================================
-- Migration 007: Remove post_date column
-- Run in: Supabase Dashboard → SQL Editor
-- ============================================================

-- Drop post_date column from jobs table
ALTER TABLE public.jobs DROP COLUMN IF EXISTS post_date;
