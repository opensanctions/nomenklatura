
CREATE EXTENSION IF NOT EXISTS hstore;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;

ALTER TABLE dataset DROP COLUMN algorithm;

ALTER TABLE entity ADD COLUMN canonical_id integer NULL REFERENCES entity (id);
ALTER TABLE entity ADD COLUMN normalized text;
ALTER TABLE entity ADD COLUMN invalid boolean DEFAULT false;
ALTER TABLE entity ADD COLUMN reviewed boolean DEFAULT false;
ALTER TABLE entity ADD COLUMN attributes hstore;

UPDATE entity SET reviewed = true;

INSERT INTO entity (dataset_id, creator_id, created_at,
    updated_at, name, canonical_id, invalid, reviewed, data)
    SELECT dataset_id, creator_id, created_at, updated_at, name,
        entity_id, is_invalid, is_matched, data FROM alias;
    

ALTER TABLE upload ADD COLUMN data BYTEA;
DELETE FROM upload;

ALTER TABLE entity DROP COLUMN data;
