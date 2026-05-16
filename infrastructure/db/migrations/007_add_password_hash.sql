-- Migration: 007_add_password_hash
-- Adds password_hash column to user_roles for UI login authentication.
ALTER TABLE user_roles ADD COLUMN IF NOT EXISTS password_hash TEXT;
