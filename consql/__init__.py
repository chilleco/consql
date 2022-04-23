"""
Initializing the Python package
"""

from .model import Attribute
from .main import make_base
from .table import Table


__version__ = '0.2'

__all__ = (
    '__version__',
    'Attribute',
    'Table',
    'make_base',
)
