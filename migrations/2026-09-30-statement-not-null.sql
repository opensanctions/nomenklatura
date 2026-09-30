--- 2026-09-30: Make statement canonical_id and external NOT NULL, as declared in make_statement_table

-- sanity check:
-- SET statement_timeout = '300s';
select count(*) from statement where canonical_id is null;  -- almost instantaneous - yay indexes
select count(*) from statement where external is null;  -- takes minutes

ALTER TABLE statement
    ALTER COLUMN canonical_id SET NOT NULL,
    ALTER COLUMN external SET NOT NULL;
