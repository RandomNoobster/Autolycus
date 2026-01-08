from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any, Dict

RSS = ['aluminum', 'bauxite', 'coal', 'food', 'gasoline', 'iron', 'lead', 'money', 'munitions', 'oil', 'steel', 'uranium', 'credits']
EMBED_COLOR = 0xff5100  # Orange color used throughout Autolycus embeds


def cut_string(string: str, length: int = 2000) -> str:
    if len(string) > length:
        return string[:length-6] + "...```"
    else:
        return string


def comma_and_list(listy: list[str]) -> str:
    if not listy:
        return ""
    if len(listy) == 1:
        return listy[0]
    return ", ".join(listy[:-1]) + " and " + listy[-1]


def get_datetime_of_turns(turns: int) -> datetime:
    now = datetime.utcnow()
    if turns == 0:
        return now
    if turns < 0:
        return (now + timedelta(hours=turns * 2 + 1 * (not bool(now.hour % 2)) + 1)).replace(minute=0, second=0, microsecond=0)
    return (now + timedelta(hours=turns * 2 - 1 * bool(now.hour % 2))).replace(minute=0, second=0, microsecond=0)


def beige_loot_value(loot_string: str, prices: dict[str, float]) -> int:
    loot_string = loot_string[loot_string.index('$'):loot_string.index('Food.')]
    loot_string = re.sub(r"[^0-9-]+", "", loot_string.replace(", ", "-"))
    rss = ['money', 'coal', 'oil', 'uranium', 'iron', 'bauxite', 'lead', 'gasoline', 'munitions', 'steel', 'aluminum', 'food']
    n = 0
    loot: dict[str, int] = {}
    for sub in loot_string.split("-"):
        loot[rss[n]] = int(sub)
        n += 1
    nation_loot = 0
    for rs in rss:
        amount = loot[rs]
        price = int(prices[rs])
        nation_loot += amount * price
    return nation_loot


def weird_division(a: float, b: float) -> float:
    return a / b if b else 0


def str_to_int(string: str) -> int:
    string = str(string).replace(",", "")
    amount: Any = string
    try:
        if "." in str(amount):
            number = re.sub("[A-z]", "", str(amount))
            amount = int(number.replace(".", "")) / 10**(len(number) - number.rfind(".") - 1)
    except (ValueError, AttributeError):
        pass
    if "k" in string.lower():
        amount = int(float(re.sub("[A-z]", "", str(amount))) * 1000)
    elif "m" in string.lower():
        amount = int(float(re.sub("[A-z]", "", str(amount))) * 1000000)
    elif "b" in string.lower():
        amount = int(float(re.sub("[A-z]", "", str(amount))) * 1000000000)
    else:
        try:
            amount = int(amount)
        except (ValueError, TypeError):
            pass
    if not isinstance(amount, int):
        raise ValueError("The provided value is not a valid amount.")
    return amount

def str_to_id_list(value: str) -> tuple[list[str], str]:
    """Convert mixed string input into list of numeric substrings and CSV."""
    value = re.sub("[^0-9]", " ", value)
    value = value.strip().replace(" ", ",")
    index = 0
    while True:
        try:
            if value[index] == value[index + 1] and not value[index].isdigit():
                value = value[:index] + value[index + 1:]
                index -= 1
            index += 1
        except Exception:
            break
    parts = [segment for segment in value.split(",") if segment]
    return parts, value


def str_to_api_key_list(value: str) -> list[str]:
    """Parse API keys from mixed strings, preserving legacy behaviour."""
    value = re.sub("[^0-9a-zA-Z]", " ", value)
    value = value.strip().replace(" ", ",")
    index = 0
    while True:
        try:
            if value[index] == value[index + 1] and not value[index].isdigit():
                value = value[:index] + value[index + 1:]
                index -= 1
            index += 1
        except Exception:
            break
    return [segment for segment in value.split(",") if segment]