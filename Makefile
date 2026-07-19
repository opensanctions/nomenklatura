TS=$(shell date +%Y%m%d%H%M)
# Produced by contrib/matcher_training/generate.py in the opensanctions repo.
ERUN_PAIRS?=data/pairs-erun.json

test:
	pytest --cov-report html --cov-report term --cov=nomenklatura tests/

typecheck:
	mypy --strict nomenklatura/

check: test typecheck

data/pairs-v1.json:
	mkdir -p data/
	curl -o data/pairs-v1.json https://data.opensanctions.org/contrib/training/pairs-v1.json

train-v1: data/pairs-v1.json
	nomenklatura train-v1-matcher data/pairs-v1.json

train-erun: $(ERUN_PAIRS)
	nomenklatura train-erun-matcher $(ERUN_PAIRS)

train: train-v1 train-erun

fixtures:
	ftm map-csv -i tests/fixtures/donations.csv -o tests/fixtures/donations.frag.ijson tests/fixtures/donations.yml
	ftm aggregate -i tests/fixtures/donations.frag.ijson -o tests/fixtures/donations.ijson
	rm tests/fixtures/donations.frag.ijson

clean:
	rm -rf data/pairs.json textual.log .coverage htmlcov dist build
