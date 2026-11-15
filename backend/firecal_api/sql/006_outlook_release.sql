-- Digest of the four export inputs shared by ingestion and the monthly outlook.
alter table release add column export_fingerprint text;
