
test:
	pytest --cov-report html --cov-report term --cov=nomenklatura tests/

typecheck:
	mypy --strict nomenklatura/ --exclude nomenklatura/tui/

check: test typecheck

data/pairs.json:
	mkdir -p data/
	curl -o data/pairs.json https://data.opensanctions.org/contrib/training/pairs.json

train: data/pairs.json
	nomenklatura train-matcher data/pairs.json

fixtures:
	ftm map-csv -i tests/fixtures/donations.csv -o tests/fixtures/donations.frag.ijson tests/fixtures/donations.yml
	ftm aggregate -i tests/fixtures/donations.frag.ijson -o tests/fixtures/donations.ijson
	rm tests/fixtures/donations.frag.ijson

clean:
	rm -rf data/pairs.json textual.log .coverage htmlcov dist build 