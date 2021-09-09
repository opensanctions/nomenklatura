
test:
	pytest --cov-report html --cov-report term --cov=nomenklatura tests/

types:
	mypy --strict nomenklatura

check: test types

fixtures:
	ftm map-csv -i tests/fixtures/donations.csv -o tests/fixtures/donations.frag.ijson tests/fixtures/donations.yml
	ftm aggregate -i tests/fixtures/donations.frag.ijson -o tests/fixtures/donations.ijson
	rm tests/fixtures/donations.frag.ijson