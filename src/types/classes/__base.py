from __future__ import annotations

__all__ = ["BaseClass"]

class BaseClass():
    def __init__(self, json, **kwargs) -> None:
        # Setting attributes
        if json:
            self.__dict__.update(json)
        else:
            self.__dict__.update(kwargs)

    def to_sql(self: object) -> tuple:
        return tuple([v for k, v in self.__dict__.items() if not k.startswith("_")])
        