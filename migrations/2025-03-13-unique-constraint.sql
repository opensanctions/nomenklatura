--- 2025-03-13: Create unique constraint on source and target id pairs

CREATE UNIQUE INDEX resolver_source_target_uniq ON resolver(source, target) WHERE deleted_at IS NULL;
