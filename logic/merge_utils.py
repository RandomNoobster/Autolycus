from __future__ import annotations
from typing import Any, Union

# Query merge helpers. Pure Python, no Discord imports.

def get_query(*queries: Union[dict[str, Any], tuple]) -> str:
    def unpack(x: tuple) -> list:
        to_return = []
        for y in x:
            if isinstance(y, tuple):
                to_return += unpack(y)
            else:
                to_return.append(y)
        return to_return

    queries = list(queries)
    for idx, query in enumerate(queries.copy()):
        if isinstance(query, tuple):
            unpacked = unpack(query)
            del queries[idx]
            queries += unpacked
    merged = list(merge(*queries).values())[0]
    query = str(merged).replace("{", "").replace("}", "").replace(",", "").replace("[", "{").replace("]","}").replace("'", "").replace(": ", "")
    return query


def merge(*queries: dict[str, Any]) -> dict[str, Any]:
    paths = []
    for query in queries:
        paths.append(list(query.keys())[0])
    if len(set(paths)) != 1:
        raise Exception(f"Paths {paths} are not the same.")
    composite_query: dict[str, Any] = {}
    for query in queries:
        for key, line in query.items():
            if key not in composite_query:
                composite_query[key] = line 
            else:
                if isinstance(line, dict):
                    composite_query[key] = merge(composite_query[key], line)
                elif isinstance(line, list):
                    for item in line:
                        if item not in composite_query[key]:
                            if isinstance(item, dict):
                                similar_item = [(x, y) for y, x in enumerate(composite_query[key]) if isinstance(x, dict) and list(item.keys())[0] in x]
                                if len(similar_item) == 0:
                                    composite_query[key].append(item)
                                else:
                                    similar_dict = similar_item[0][0]
                                    similar_idx = similar_item[0][1]
                                    composite_query[key][similar_idx] = (merge(similar_dict, item))
                            elif isinstance(item, str):
                                composite_query[key].append(item)
                            else:
                                raise Exception(f"Value {item} is not a dictionary or a string.")
                else:
                    raise Exception(f"Value {line} is not a dictionary or a list.")
    return composite_query
