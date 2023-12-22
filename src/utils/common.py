import logging
import re
from datetime import datetime, timedelta
from typing import Union
import pymongo


__all__ = (
    "LOGGER",
    "get_date_from_string",
    "cut_string",
    "comma_and_list",
    "get_datetime_of_turns",
    "listify",
    "str_to_id_list",
    "str_to_api_key_list",
    "weird_division",
    "str_to_int",
)


logging.basicConfig(filename="logs.log", filemode='a', format='%(levelname)s %(asctime)s.%(msecs)d %(name)s: %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO)
LOGGER = logging.getLogger()


def get_date_from_string(date: Union[str, datetime]) -> datetime:
    """
    Returns a datetime object from a string. If the string is already a datetime object, it will return the datetime object.
    """
    if isinstance(date, datetime):
        return date
    return datetime.strptime(date, "%Y-%m-%dT%H:%M:%S%z").replace(tzinfo=None)


def cut_string(string: str, length: int = 2000) -> str:
    """
    Cuts a string to a certain length, adding an ellipsis at the end if the string is longer than the length.
    """
    if len(string) > length:
        return string[:length-6] + "...```"
    else:
        return string


def comma_and_list(listy: list) -> str:
    """
    Returns a string with a comma and an "and" before the last item in the list.
    """
    if len(listy) == 0:
        return ""
    elif len(listy) == 1:
        return listy[0]
    else:
        return "{} and {}".format(", ".join(listy[:-1]),  listy[-1])


def get_datetime_of_turns(turns: int) -> datetime:
    """
    Returns the datetime of the next turn. If turns is 0, it will return the current datetime.
    """
    now = datetime.utcnow()
    if turns == 0:
        return now
    elif turns < 0:
        return (now + timedelta(hours=turns * 2 + 1 * (not bool(now.hour % 2)) + 1)).replace(minute=0, second=0, microsecond=0)
    else:
        return (now + timedelta(hours=turns * 2 - 1 * bool(now.hour % 2))).replace(minute=0, second=0, microsecond=0)


async def listify(cursor: pymongo.cursor.Cursor):
    """
    Returns a list from a pymongo cursor.
    """
    new_list = []
    async for x in cursor:
        new_list.append(x)
    return new_list


def str_to_id_list(str_var: str) -> list[int]:
    """
    Returns a list of integers from a string. The string can be a list of integers separated by commas or spaces, or a string of integers with no spaces or commas.
    """
    try:
        str_var = re.sub("[^0-9]", " ", str_var)
        str_var = str_var.strip().replace(" ", ",")
        index = 0
        while True:
            try:
                if str_var[index] == str_var[index+1] and not str_var[index].isdigit():
                    str_var = str_var[:index] + str_var[index+1:]
                    index -= 1
                index += 1
            except Exception as e:
                break
        return str_var.split(","), str_var
    except Exception as e:
        LOGGER.error(e, exc_info=True)
        raise e


def str_to_api_key_list(str_var: str) -> list[str]:
    """
    Returns a list of api keys from a string. The string can be a list of api keys separated by commas or spaces, or a string of api keys with no spaces or commas.
    """
    try:
        str_var = re.sub("[^0-9a-zA-Z]", " ", str_var)
        str_var = str_var.strip().replace(" ", ",")
        index = 0
        while True:
            try:
                if str_var[index] == str_var[index+1] and not str_var[index].isdigit():
                    str_var = str_var[:index] + str_var[index+1:]
                    index -= 1
                index += 1
            except Exception as e:
                break
        return str_var.split(",")
    except Exception as e:
        LOGGER.error(e, exc_info=True)
        raise e


def weird_division(a: float, b: float) -> float:
    """
    Divides two numbers, returning 0 if the denominator is 0.
    """
    return a / b if b else 0


def str_to_int(string: str) -> int:
    """
    Converts a string to an integer.
    :param string: String to be converted.
    :return: The integer value of the string.
    """
    string = str(string)
    amount = string
    try:
        if "." in amount:
            number = re.sub("[A-z,]", "", amount)
            amount = int(number.replace(".", "")) / \
                10**(len(number) - number.rfind(".") - 1)
    except:
        pass

    if "k" in string.lower():
        amount = int(float(re.sub("[A-z]", "", str(amount))) * 1000)
    if "m" in string.lower():
        amount = int(float(re.sub("[A-z]", "", str(amount))) * 1000000)
    if "b" in string.lower():
        amount = int(float(re.sub("[A-z]", "", str(amount))) * 1000000000)
    else:
        try:
            amount = int(amount)
        except:
            pass

    if not isinstance(amount, int):
        raise ValueError("The provided value is not a valid amount.")

    return amount
