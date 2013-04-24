
ALTER TABLE link RENAME COLUMN value_id TO entity_id;
ALTER TABLE link RENAME TO alias;
ALTER TABLE value RENAME TO entity;
ALTER TABLE entity RENAME COLUMN value TO name;

