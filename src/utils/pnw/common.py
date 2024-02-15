import asyncio
import aiohttp
from typing import Union
from ...env import API_KEY, BOT_KEY
from .. import LOGGER
from ...types import ResourceWrapper, Nation, Alliance


async def paginate_call(data: str, path: str, key: str = API_KEY) -> Union[dict, aiohttp.ClientResponse]:
    """
    Paginates a call to the API. Must include `page:page_number` in the query.
    `data` is the GraphQL query.
    `path` is the path to the information (`alliances`, `nations` etc).
    `key` is the API key.
    """
    n = 0
    has_more_pages = True
    data_to_return = []

    while has_more_pages:
        n += 1
        response = await call(data.replace("page_number", str(n), 1), key)
        data_to_return += response['data'][path]['data']
        has_more_pages = response['data'][path]['paginatorInfo']['hasMorePages']

    return data_to_return


async def call(data: str, key: str = API_KEY, retry_limit: int = 2, use_bot_key=False) -> Union[dict, aiohttp.ClientResponse]:
    async with aiohttp.ClientSession() as session:
        retry = 0
        while True:
            if use_bot_key:
                headers = {'X-Bot-Key': BOT_KEY, 'X-Api-Key': API_KEY}
            else:
                headers = {}
            async with session.post(f'https://api.politicsandwar.com/graphql?api_key={key}', json={"query": data}, headers=headers) as response:
                if "X-Ratelimit-Remaining" in response.headers:
                    if response.headers['X-Ratelimit-Remaining'] == '0':
                        await asyncio.sleep(int(response.headers['X-Ratelimit-Reset-After']))
                        continue
                elif "Retry-After" in response.headers:
                    await asyncio.sleep(int(response.headers['Retry-After']))
                    continue
                try:
                    json_response = await response.json()
                except aiohttp.ContentTypeError:
                    raise Exception("Attempt to decode JSON with unexpected mimetype: " + await response.text())
                if response.status == 401:
                    if "error" in json_response:
                        if "invalid api_key" in json_response["error"]["errors"][0]["message"]:
                            raise ConnectionError("Invalid API key.")
                if "data" not in json_response and use_bot_key == False:
                    if retry < retry_limit:
                        retry += 1
                        await asyncio.sleep(1)
                        continue
                    elif "error" in json_response:
                        raise Exception(json_response["error"])
                    elif "errors" in json_response:
                        raise Exception(json_response["errors"])
                return json_response


async def withdraw(api_key: str, recipient: Union[Nation, Alliance], resources: ResourceWrapper, note: str = "") -> bool:
    try:
        if isinstance(recipient, Nation):
            call_string = f"receiver:{recipient.id} receiver_type:1"
        elif isinstance(recipient, Alliance):
            call_string = f"receiver:{recipient.id} receiver_type:2"
        else:
            raise Exception("Recipient must be a Nation or an Alliance.")

        for resource, amount in resources:
            call_string += f"{resource}:{amount} "
        call_string += f"note:\"{note}\""

        res = await call(f"mutation{{bankWithdraw({call_string}){{id}}}}", api_key, use_bot_key=True)

        if "errors" in res:
            raise Exception(res["errors"])

        return True

    except Exception as e:
        LOGGER.error(
            f"Error withdrawing resources.\nApi key: {api_key}\nResources: {resources}\nError: {e}", exc_info=True)
        return False


def get_query(*queries: Union[dict, tuple]) -> str:
    """
    Takes one or multiple queries and merges them into one query. Return the query as a string that can be fed into the PnW API.
    """
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
    query = str(merged).replace("{", "").replace("}", "").replace(",", "").replace(
        "[", "{").replace("]", "}").replace("'", "").replace(": ", "")
    return query


def merge(*queries: dict) -> dict:
    """
    Takes a list of queries and merges them. Returns them as a dictionary.
    """
    paths = []
    for query in queries:
        paths.append(list(query.keys())[0])
    if len(set(paths)) != 1:
        raise Exception(f"Paths {paths} are not the same.")
    composite_query = {}  # the composite query to return
    for query in queries:  # for each query
        for key, line in query.items():  # nations, cities etc
            if key not in composite_query:  # the key is NOT in the composite query yet
                composite_query[key] = line
            else:  # the key is already in the composite query
                if isinstance(line, dict):  # the value is a dictionary
                    # merge the two dictionaries
                    composite_query[key] = merge(composite_query[key], line)
                elif isinstance(line, list):  # the value is a list
                    for item in line:  # for each item in the line
                        # if the item is not in the composite query
                        if item not in composite_query[key]:
                            if isinstance(item, dict):  # if the item is a dictionary
                                similar_item = [(x, y) for y, x in enumerate(composite_query[key]) if isinstance(
                                    x, dict) and list(item.keys())[0] in x]  # find similar items
                                if len(similar_item) == 0:  # if there are no similar items
                                    # add the item to the composite query
                                    composite_query[key].append(item)
                                else:  # if there are similar items
                                    # get the similar dictionary
                                    similar_dict = similar_item[0][0]
                                    # get the index of the similar dictionary
                                    similar_idx = similar_item[0][1]
                                    # merge the similar dictionary with the item
                                    composite_query[key][similar_idx] = (
                                        merge(similar_dict, item))
                            elif isinstance(item, str):  # if the item is a string
                                # add the item to the composite query
                                composite_query[key].append(item)
                            else:  # the value is wrong
                                raise Exception(
                                    f"Value {item} is not a dictionary or a string.")
                else:  # the value is wrong
                    raise Exception(
                        f"Value {line} is not a dictionary or a list.")
    return composite_query
