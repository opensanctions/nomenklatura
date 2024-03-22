from fixture_gen.generators import create_fixtures_with_treatment
from pathlib import Path


def test_fixture_creation():
    p = Path(__file__).parent / "fixtures" / "generated" / "test_pairs.json"
    assert p.exists() is False
    create_fixtures_with_treatment("duplicate_random_character", p, n=100)
    assert p.exists() is True
    assert p.stat().st_size > 0
    p.unlink()
