"""
The layer for initializing the database
"""

# from ._db import get_db
from .model import BaseModel


def make_base(host, name, login=None, password=None):
    """ Declare the base class of the model """

    class Base(BaseModel):
        """ Base model with the initialized database """

        # _db = get_db(host, name, login, password)
        database = name

        @property
        def _name(self) -> str:
            """ Table name """
            return None

    return Base
