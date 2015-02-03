#!/bin/bash

gosu postgres postgres --single -jE $POSTGRES_USER <<-EOSQL
	CREATE EXTENSION hstore;
	CREATE EXTENSION fuzzystrmatch;
EOSQL
