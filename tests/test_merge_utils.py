"""Tests for logic.merge_utils query building."""
import copy

from logic import queries
from logic.merge_utils import get_query

_TUPLE_AND_DICT_QUERIES = {
    name: value
    for name, value in vars(queries).items()
    if name.isupper() and isinstance(value, (dict, tuple))
}


def test_get_query_never_modifies_the_shared_query_constants():
    before = copy.deepcopy(_TUPLE_AND_DICT_QUERIES)
    first_nuke_query = get_query(queries.NUKETARGETS)

    get_query(queries.WAR_STATUS)
    get_query(queries.WHO)
    get_query(queries.BATTLE_CALC)

    assert _TUPLE_AND_DICT_QUERIES == before
    # The bot's paginated nuke-target scan keeps asking for the same fields.
    assert get_query(queries.NUKETARGETS) == first_nuke_query


def test_get_query_is_stable_across_repeated_calls():
    assert get_query(queries.WAR_STATUS) == get_query(queries.WAR_STATUS)
