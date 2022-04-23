from .errors import ErrorInvalid


class Table:
    """ Table info """

    _name: str
    _schema = None
    _pkey = None
    _keys = None
    _conflict = None
    _conflict_keyname = None

    @property
    def primary_key(self):
        if len(self.pkey) == 1:
            return self.pkey[0]
        return self.pkey

    @property
    def name(self):
        return self._name

    @property
    def schema(self):
        return self._schema

    @property
    def pkey(self):
        return self._pkey

    @property
    def keys(self):
        return self._keys

    @property
    def conflict_key(self):
        return self._conflict

    @property
    def conflict_keyname(self):
        return self._conflict_keyname

    def __init__(self, name, pkey='id', keys=None, conflict=None, schema=None):
        self._name = name
        self._schema = schema

        if isinstance(pkey, str):
            self._pkey = (pkey,)
        else:
            self._pkey = tuple(pkey)

        if not keys:
            keys = {}

        for key in keys.keys():
            if isinstance(keys[key], str):
                keys[key] = (keys[key],)
            else:
                keys[key] = tuple(keys[key])

        self._keys = keys

        if conflict:
            if conflict not in self.keys:
                raise ErrorInvalid(conflict)

            self._conflict = self.keys[conflict]
            self._conflict_keyname = conflict

        else:
            self._conflict = None
            self._conflict_keyname = None
