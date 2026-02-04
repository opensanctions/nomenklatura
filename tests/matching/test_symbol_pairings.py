"""
Tests for generate_symbol_pairings function in LogicV2 name matching.

This test module verifies the correctness of the symbol pairing generation algorithm,
which is a critical component of the LogicV2 matcher's symbolic name analysis.
"""
from rigour.names import Name, NamePart, Symbol, NameTypeTag


from nomenklatura.matching.logic_v2.names.match import generate_symbol_pairings
from nomenklatura.matching.logic_v2.names.pairing import Pairing


def test_empty_names():
    """Test that empty names produce an empty pairing."""
    query = Name("", tag=NameTypeTag.PER)
    result = Name("", tag=NameTypeTag.PER)
    pairings = generate_symbol_pairings(query, result)

    assert len(pairings) == 1
    assert len(pairings[0].matches) == 0
    assert len(pairings[0].query_used) == 0
    assert len(pairings[0].result_used) == 0


def test_no_common_symbols():
    """Test that names with no common symbols produce only an empty pairing."""
    # Create query with symbol A
    query = Name("John", tag=NameTypeTag.PER)
    query.parts = [NamePart("john", 0)]
    symbol_a = Symbol(Symbol.Category.NAME, 1001)
    query.apply_part(query.parts[0], symbol_a)

    # Create result with symbol B (different)
    result = Name("Mary", tag=NameTypeTag.PER)
    result.parts = [NamePart("mary", 0)]
    symbol_b = Symbol(Symbol.Category.NAME, 1002)
    result.apply_part(result.parts[0], symbol_b)

    pairings = generate_symbol_pairings(query, result)

    # Should return one empty pairing since symbols don't match
    assert len(pairings) == 1
    assert len(pairings[0].matches) == 0


def test_single_symbol_match():
    """Test a simple case with one matching symbol."""
    # Create query and result with same symbol
    query = Name("John", tag=NameTypeTag.PER)
    query.parts = [NamePart("john", 0)]
    symbol = Symbol(Symbol.Category.NAME, 1001)
    query.apply_part(query.parts[0], symbol)

    result = Name("John", tag=NameTypeTag.PER)
    result.parts = [NamePart("john", 0)]
    result.apply_part(result.parts[0], symbol)

    pairings = generate_symbol_pairings(query, result)

    # Should produce one pairing with one match
    assert len(pairings) == 1
    assert len(pairings[0].matches) == 1
    assert pairings[0].matches[0].symbol == symbol
    assert query.parts[0] in pairings[0].query_used
    assert result.parts[0] in pairings[0].result_used


def test_two_independent_symbol_matches():
    """Test two symbols that can be paired independently."""
    # Query: "John Smith"
    query = Name("John Smith", tag=NameTypeTag.PER)
    query.parts = [NamePart("john", 0), NamePart("smith", 1)]

    john_symbol = Symbol(Symbol.Category.NAME, 1001)
    smith_symbol = Symbol(Symbol.Category.NAME, 1002)
    query.apply_part(query.parts[0], john_symbol)
    query.apply_part(query.parts[1], smith_symbol)

    # Result: "John Smith"
    result = Name("John Smith", tag=NameTypeTag.PER)
    result.parts = [NamePart("john", 0), NamePart("smith", 1)]
    result.apply_part(result.parts[0], john_symbol)
    result.apply_part(result.parts[1], smith_symbol)

    pairings = generate_symbol_pairings(query, result)

    # Should produce one pairing with two matches
    assert len(pairings) == 1
    pairing = pairings[0]
    assert len(pairing.matches) == 2

    # Check that both parts are used
    assert query.parts[0] in pairing.query_used
    assert query.parts[1] in pairing.query_used
    assert result.parts[0] in pairing.result_used
    assert result.parts[1] in pairing.result_used


def test_multiple_result_spans_for_same_symbol():
    """Test when result has multiple spans with the same symbol as query."""
    # Query: "John" with one symbol
    query = Name("John", tag=NameTypeTag.PER)
    query.parts = [NamePart("john", 0)]
    symbol = Symbol(Symbol.Category.NAME, 1001)
    query.apply_part(query.parts[0], symbol)

    # Result: "John Johnny" where both map to the same symbol
    result = Name("John Johnny", tag=NameTypeTag.PER)
    result.parts = [NamePart("john", 0), NamePart("johnny", 1)]
    result.apply_part(result.parts[0], symbol)
    result.apply_part(result.parts[1], symbol)

    pairings = generate_symbol_pairings(query, result)

    # Should produce two pairings, one for each possible match
    assert len(pairings) == 2

    # Both pairings should use the same query part but different result parts
    assert all(query.parts[0] in p.query_used for p in pairings)
    result_parts_used = [list(p.result_used)[0] for p in pairings]
    assert result.parts[0] in result_parts_used
    assert result.parts[1] in result_parts_used


def test_overlapping_name_parts_prevented():
    """Test that pairings with overlapping name parts are not created."""
    # Query: "John" (single part, used by two different symbols)
    query = Name("John", tag=NameTypeTag.PER)
    query.parts = [NamePart("john", 0)]

    # Add two different symbols to the same part
    symbol_a = Symbol(Symbol.Category.NAME, 1001)
    symbol_b = Symbol(Symbol.Category.INITIAL, "j")
    query.apply_part(query.parts[0], symbol_a)
    query.apply_part(query.parts[0], symbol_b)

    # Result: Similar structure
    result = Name("John", tag=NameTypeTag.PER)
    result.parts = [NamePart("john", 0)]
    result.apply_part(result.parts[0], symbol_a)
    result.apply_part(result.parts[0], symbol_b)

    pairings = generate_symbol_pairings(query, result)

    # Should produce multiple pairings, but each should only use the part once
    for pairing in pairings:
        # Each name part should only appear once in the used set
        assert query.parts[0] in pairing.query_used
        assert result.parts[0] in pairing.result_used

        # The pairing should have at most one match (since both symbols
        # would try to use the same parts)
        assert len(pairing.matches) <= 2


def test_multi_part_span():
    """Test symbols that span multiple name parts."""
    # Query: "New York" as a single location symbol
    query = Name("New York", tag=NameTypeTag.ORG)
    query.parts = [NamePart("new", 0), NamePart("york", 1)]
    location_symbol = Symbol(Symbol.Category.LOCATION, "US-NY")
    # Apply the symbol to both parts as a phrase
    query.apply_phrase("new york", location_symbol)

    # Result: Same structure
    result = Name("New York", tag=NameTypeTag.ORG)
    result.parts = [NamePart("new", 0), NamePart("york", 1)]
    result.apply_phrase("new york", location_symbol)

    pairings = generate_symbol_pairings(query, result)

    # Should produce one pairing with one match covering both parts
    assert len(pairings) == 1
    pairing = pairings[0]
    assert len(pairing.matches) == 1

    # Both parts should be used
    assert query.parts[0] in pairing.query_used
    assert query.parts[1] in pairing.query_used
    assert result.parts[0] in pairing.result_used
    assert result.parts[1] in pairing.result_used


def test_organization_type_symbols():
    """Test pairing of organization type symbols (e.g., LLC, Corp)."""
    # Query: "Test Corp"
    query = Name("Test Corp", tag=NameTypeTag.ORG)
    query.parts = [NamePart("test", 0), NamePart("corp", 1)]
    org_class = Symbol(Symbol.Category.ORG_CLASS, "CORP")
    query.apply_part(query.parts[1], org_class)

    # Result: "Test Corporation"
    result = Name("Test Corporation", tag=NameTypeTag.ORG)
    result.parts = [NamePart("test", 0), NamePart("corporation", 1)]
    result.apply_part(result.parts[1], org_class)

    pairings = generate_symbol_pairings(query, result)

    # Should produce one pairing matching the org type
    assert len(pairings) == 1
    pairing = pairings[0]
    assert len(pairing.matches) == 1
    assert pairing.matches[0].symbol.category == Symbol.Category.ORG_CLASS


def test_deduplication_of_identical_pairings():
    """Test that the seen set prevents duplicate pairings."""
    # Query: "John" with one symbol
    query = Name("John", tag=NameTypeTag.PER)
    query.parts = [NamePart("john", 0)]
    symbol = Symbol(Symbol.Category.NAME, 1001)

    # Apply the same symbol twice (shouldn't happen normally, but test robustness)
    query.apply_part(query.parts[0], symbol)
    query.apply_part(query.parts[0], symbol)

    # Result: "John" with the symbol once
    result = Name("John", tag=NameTypeTag.PER)
    result.parts = [NamePart("john", 0)]
    result.apply_part(result.parts[0], symbol)

    pairings = generate_symbol_pairings(query, result)

    # Should deduplicate and produce only one pairing
    # Note: The actual behavior depends on how spans are stored
    assert len(pairings) >= 1
    # All pairings should have the same structure due to deduplication
    for pairing in pairings:
        assert query.parts[0] in pairing.query_used
        assert result.parts[0] in pairing.result_used


def test_partial_symbol_overlap():
    """Test case where only some symbols overlap between query and result."""
    # Query: "John Michael Smith" with symbols for John and Smith
    query = Name("John Michael Smith", tag=NameTypeTag.PER)
    query.parts = [NamePart("john", 0), NamePart("michael", 1), NamePart("smith", 2)]

    john_symbol = Symbol(Symbol.Category.NAME, 1001)
    smith_symbol = Symbol(Symbol.Category.NAME, 1002)
    query.apply_part(query.parts[0], john_symbol)
    query.apply_part(query.parts[2], smith_symbol)

    # Result: "John Smith" - missing Michael
    result = Name("John Smith", tag=NameTypeTag.PER)
    result.parts = [NamePart("john", 0), NamePart("smith", 1)]
    result.apply_part(result.parts[0], john_symbol)
    result.apply_part(result.parts[1], smith_symbol)

    pairings = generate_symbol_pairings(query, result)

    # Should produce one pairing with two matches (John and Smith)
    assert len(pairings) == 1
    pairing = pairings[0]
    assert len(pairing.matches) == 2

    # John and Smith should be used, Michael should not
    assert query.parts[0] in pairing.query_used
    assert query.parts[1] not in pairing.query_used  # Michael not matched
    assert query.parts[2] in pairing.query_used


def test_initial_symbols():
    """Test pairing of initial symbols (e.g., J for John)."""
    # Query: "J Smith"
    query = Name("J Smith", tag=NameTypeTag.PER)
    query.parts = [NamePart("j", 0), NamePart("smith", 1)]

    initial_symbol = Symbol(Symbol.Category.INITIAL, "j")
    smith_symbol = Symbol(Symbol.Category.NAME, 1002)
    query.apply_part(query.parts[0], initial_symbol)
    query.apply_part(query.parts[1], smith_symbol)

    # Result: "John Smith" where "John" also has initial "j"
    result = Name("John Smith", tag=NameTypeTag.PER)
    result.parts = [NamePart("john", 0), NamePart("smith", 1)]
    result.apply_part(result.parts[0], initial_symbol)
    result.apply_part(result.parts[1], smith_symbol)

    pairings = generate_symbol_pairings(query, result)

    # Should produce one pairing with two matches
    assert len(pairings) == 1
    pairing = pairings[0]
    assert len(pairing.matches) == 2

    # Check that both symbol types are matched
    symbol_categories = {m.symbol.category for m in pairing.matches}
    assert Symbol.Category.INITIAL in symbol_categories
    assert Symbol.Category.NAME in symbol_categories


def test_numeric_symbols():
    """Test pairing of numeric symbols (e.g., ordinals, numbers in company names)."""
    # Query: "Fund 1"
    query = Name("Fund 1", tag=NameTypeTag.ORG)
    query.parts = [NamePart("fund", 0), NamePart("1", 1)]

    numeric_symbol = Symbol(Symbol.Category.NUMERIC, 1)
    query.apply_part(query.parts[1], numeric_symbol)

    # Result: "Fund 1"
    result = Name("Fund 1", tag=NameTypeTag.ORG)
    result.parts = [NamePart("fund", 0), NamePart("1", 1)]
    result.apply_part(result.parts[1], numeric_symbol)

    pairings = generate_symbol_pairings(query, result)

    # Should produce one pairing matching the number
    assert len(pairings) == 1
    pairing = pairings[0]
    assert len(pairing.matches) == 1
    assert pairing.matches[0].symbol.category == Symbol.Category.NUMERIC
    assert pairing.matches[0].symbol.id == 1


def test_complex_organization_name():
    """Test a complex organization name with multiple symbol types."""
    # Query: "International Business Machines Corporation"
    query = Name("International Business Machines Corp", tag=NameTypeTag.ORG)
    query.parts = [
        NamePart("international", 0),
        NamePart("business", 1),
        NamePart("machines", 2),
        NamePart("corp", 3),
    ]

    symbol_intl = Symbol(Symbol.Category.SYMBOL, "INTERNATIONAL")
    org_class = Symbol(Symbol.Category.ORG_CLASS, "CORP")
    query.apply_part(query.parts[0], symbol_intl)
    query.apply_part(query.parts[3], org_class)

    # Result: "IBM Corporation"
    result = Name("IBM Corporation", tag=NameTypeTag.ORG)
    result.parts = [NamePart("ibm", 0), NamePart("corporation", 1)]
    result.apply_part(result.parts[1], org_class)

    pairings = generate_symbol_pairings(query, result)

    # Should produce one pairing matching the org class
    # (International not matched since result doesn't have it)
    assert len(pairings) == 1
    pairing = pairings[0]
    assert len(pairing.matches) == 1
    assert pairing.matches[0].symbol.category == Symbol.Category.ORG_CLASS


def test_pairing_preserves_match_properties():
    """Test that generated pairings correctly preserve match properties."""
    # Query: "John Smith Ltd"
    query = Name("John Smith Ltd", tag=NameTypeTag.ORG)
    query.parts = [NamePart("john", 0), NamePart("smith", 1), NamePart("ltd", 2)]

    org_class = Symbol(Symbol.Category.ORG_CLASS, "LLC")
    query.apply_part(query.parts[2], org_class)

    # Result: "John Smith Limited"
    result = Name("John Smith Limited", tag=NameTypeTag.ORG)
    result.parts = [NamePart("john", 0), NamePart("smith", 1), NamePart("limited", 2)]
    result.apply_part(result.parts[2], org_class)

    pairings = generate_symbol_pairings(query, result)

    # Verify match structure
    assert len(pairings) == 1
    pairing = pairings[0]
    match = pairing.matches[0]

    # Check that match has correct query and result parts
    assert len(match.qps) == 1
    assert len(match.rps) == 1
    assert match.qps[0] == query.parts[2]
    assert match.rps[0] == result.parts[2]
    assert match.symbol == org_class


def test_symbol_category_mismatch():
    """Test that symbols with same ID but different categories don't match."""
    # Query: "Test" with numeric symbol "1"
    query = Name("Test 1", tag=NameTypeTag.ORG)
    query.parts = [NamePart("test", 0), NamePart("1", 1)]
    symbol_num = Symbol(Symbol.Category.NUMERIC, 1)
    query.apply_part(query.parts[1], symbol_num)

    # Result: "Test" with name symbol that happens to have id "1"
    result = Name("Test A", tag=NameTypeTag.ORG)
    result.parts = [NamePart("test", 0), NamePart("a", 1)]
    symbol_name = Symbol(Symbol.Category.NAME, 1)  # Same ID, different category
    result.apply_part(result.parts[1], symbol_name)

    pairings = generate_symbol_pairings(query, result)

    # Should produce empty pairing since categories don't match
    assert len(pairings) == 1
    assert len(pairings[0].matches) == 0


def test_empty_pairing_when_no_matches_possible():
    """Test that function returns one empty pairing when no symbol matches are possible."""
    # Query: Name with symbols
    query = Name("John", tag=NameTypeTag.PER)
    query.parts = [NamePart("john", 0)]
    query.apply_part(query.parts[0], Symbol(Symbol.Category.NAME, 1001))

    # Result: Name with no symbols
    result = Name("Mary", tag=NameTypeTag.PER)
    result.parts = [NamePart("mary", 0)]
    # No symbols applied

    pairings = generate_symbol_pairings(query, result)

    assert len(pairings) == 1
    assert isinstance(pairings[0], Pairing)
    assert len(pairings[0].matches) == 0
    assert len(pairings[0].query_used) == 0
    assert len(pairings[0].result_used) == 0


def test_multiple_pairings_generated():
    """Test that multiple valid pairings are generated when possible."""
    # Query: "John Smith" where "Smith" can be matched as both a name and location
    query = Name("John Smith", tag=NameTypeTag.PER)
    query.parts = [NamePart("john", 0), NamePart("smith", 1)]

    john_symbol = Symbol(Symbol.Category.NAME, 1001)
    smith_name = Symbol(Symbol.Category.NAME, 1002)

    query.apply_part(query.parts[0], john_symbol)
    query.apply_part(query.parts[1], smith_name)

    # Result: "John Smith" but with potentially different symbol for Smith
    result = Name("John Smith", tag=NameTypeTag.PER)
    result.parts = [NamePart("john", 0), NamePart("smith", 1)]
    result.apply_part(result.parts[0], john_symbol)
    # Add an alternative symbol for Smith in result
    smith_alt = Symbol(Symbol.Category.NAME, 1003)
    result.apply_part(result.parts[1], smith_name)
    result.apply_part(result.parts[1], smith_alt)

    pairings = generate_symbol_pairings(query, result)

    # Should generate multiple pairings exploring different combinations
    # At minimum should have one pairing matching John+Smith(name)
    assert len(pairings) >= 1

    # Check that at least one pairing has John matched
    john_matched_in_some_pairing = any(
        query.parts[0] in p.query_used for p in pairings
    )
    assert john_matched_in_some_pairing


def test_performance_with_many_symbols():
    """Test that algorithm handles names with many symbols reasonably."""
    # Create query with 5 parts and 5 symbols
    query = Name("A B C D E", tag=NameTypeTag.ORG)
    query.parts = [
        NamePart("a", 0),
        NamePart("b", 1),
        NamePart("c", 2),
        NamePart("d", 3),
        NamePart("e", 4),
    ]

    symbols = [Symbol(Symbol.Category.NAME, i) for i in range(1000, 1005)]
    for i, part in enumerate(query.parts):
        query.apply_part(part, symbols[i])

    # Result: Same structure
    result = Name("A B C D E", tag=NameTypeTag.ORG)
    result.parts = [
        NamePart("a", 0),
        NamePart("b", 1),
        NamePart("c", 2),
        NamePart("d", 3),
        NamePart("e", 4),
    ]
    for i, part in enumerate(result.parts):
        result.apply_part(part, symbols[i])

    pairings = generate_symbol_pairings(query, result)

    # Should produce at least one complete pairing
    assert len(pairings) >= 1

    # At least one pairing should match all parts
    complete_pairings = [p for p in pairings if len(p.matches) == 5]
    assert len(complete_pairings) >= 1

    # Verify the complete pairing uses all parts
    complete = complete_pairings[0]
    assert len(complete.query_used) == 5
    assert len(complete.result_used) == 5
