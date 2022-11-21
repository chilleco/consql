"""
Initializing the Python package
"""

from .model import Attribute, Extra
from .main import make_base
from .table import Table


__version__ = '0.15'

__all__ = (
    '__version__',
    'Attribute',
    'Extra',
    'Table',
    'make_base',
)
