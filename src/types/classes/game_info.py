from __future__ import annotations
from enums import *
from ...utils import get_date_from_string
from . import BaseClass


__all__ = ["Radiation"]


class Radiation(BaseClass):
    def __init__(self, json: dict = None, **kwargs):
        BaseClass.__init__(self, json, **kwargs)

        # Ensuring types
        self._international = float(self.__getattribute__("global"))
        self.north_america = float(self.north_america)
        self.south_america = float(self.south_america)
        self.europe = float(self.europe)
        self.africa = float(self.africa)
        self.asia = float(self.asia)
        self.australia = float(self.australia)
        self.antarctica = float(self.antarctica)

   
