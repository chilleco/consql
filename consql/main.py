"""
The layer for initializing the database
"""

from libdev.cfg import set_cfg
from .model import BaseModel


def make_base(host, name, login=None, password=None):
    """ Declare the base class of the model """

    set_cfg('consql.host', host)
    set_cfg('consql.user', login)
    set_cfg('consql.pass', password)
    set_cfg('consql.db', name)

    class Base(BaseModel):
        """ Base model with the initialized database """

        database = name

        @property
        def _name(self) -> str:
            """ Table name """
            return None

    return Base
