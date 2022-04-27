import os
import os.path
import copy
import re
import time
import base64
import hashlib
from abc import abstractmethod

from .errors import ErrorInvalid, ErrorWrong, ErrorRequest
from ._db import dbh
from ._sql import sqlt
from . import _json as json


TOKEN = ''
CURSOR_LIMIT = 100


def enum(data):
    if not isinstance(data, (tuple, list, set)) or not data:
        raise ValueError('Enum exception')

    data = set(data)

    def check(value, self=None, field=None):
        if isinstance(value, (list, tuple, set)):
            for v in value:
                if v not in data:
                    return False

            return True

        return value in data

    return check

def pack(salt: str, **kwargs):
    data = json.dumps(kwargs)
    data = base64.b64encode(data.encode()).decode()

    if salt is None:
        salt = ''

    data_salt = data + salt

    sign = hashlib.sha1(data_salt.encode()).hexdigest()
    return data + '.' + sign

def unpack(salt: str, token: str):
    if not isinstance(token, str):
        return None

    if salt is None:
        salt = ''

    try:
        data, sign = token.split('.', 1)
    except ValueError:
        return None
    if not sign:
        return None

    data_salt = data + salt
    sign_check = hashlib.sha1(data_salt.encode()).hexdigest()

    if sign_check != sign:
        return None

    payload = base64.b64decode(data)
    result = json.loads(payload)

    return result


class Attribute:
    """ Descriptor """

    name: str = None
    types = None
    default = None
    coerce = None
    always: bool = False
    required: bool = None
    tags: list = None
    plugins: dict = None
    validators: dict = None

    def __get__(self, instance, owner):
        if instance is None:
            return self

        if not self.name:
            return None

        return instance.__dict__.get(self.name)

    def __set_name__(self, instance, name):
        self.name = name

    def _check(self, value):
        if value is None:
            return True

        for type_ in self.types:
            if isinstance(type_, str):
                if value.__class__.__name__ == type_:
                    return True
                continue

            if isinstance(value, type_):
                return True

        return False

    def __set__(self, instance, value):
        if self._check(value) and not self.always:
            new_value = value

        else:
            if self.name not in instance.__dict__:
                new_value = self.coerce(value)

            else:
                try:
                    new_value = self.coerce(value)
                except ErrorRequest:
                    new_value = self.coerce(value, self=instance, field=self)

        if new_value is not None:
            if not self._check(new_value):
                raise ErrorInvalid(self.name)

        if new_value is None:
            if self.required:
                raise ErrorInvalid(self.name)

        if new_value is not None or self.required:
            for validator_name, validate in self.validators.items():
                if self.name not in instance.__dict__:
                    if validate(new_value):
                        continue
                else:
                    try:
                        if validate(new_value):
                            continue
                    except ErrorRequest:
                        if validate(new_value, self=instance, field=self):
                            continue

                raise ErrorInvalid(
                    f'{self.name}#{validator_name}: {new_value}'
                )

        self._update_rehashed(instance, self.name, new_value)
        instance.__dict__[self.name] = new_value

    @staticmethod
    def _update_rehashed(owner, name, new_value):
        old_value = getattr(owner, name)

        if type(old_value) is type(new_value):
            if old_value == new_value:
                return

        owner._rehashed.add(name)

    def __init__(
        self,
        types,
        required=False,
        coerce=None,
        tags=None,
        default=None,
        always=False,
        **plugins,
    ):
        self.required = required
        if not isinstance(types, (tuple, set, list)):
            types = [ types ]
        self.types = tuple(types)

        if callable(coerce):
            if coerce in {str, float, int, bool}:
                self.coerce = lambda v: None if v is None else coerce(v)
            else:
                self.coerce = coerce
        elif coerce is not None:
            raise ValueError('coerce')
        else:
            self.coerce = lambda x: x

        if callable(default):
            self.default = default
        else:
            self.default = lambda *args, **kwargs: default

        if tags is not None:
            if isinstance(tags, (list, tuple, set)):
                tags = list(tags)
            elif isinstance(tags, str):
                tags = [tags]
            self.tags = tags
        else:
            self.tags = []

        self.plugins = plugins
        self.validators = {}
        self.always = bool(always)


class Meta:
    fields = None
    _subclass_attributes = None

    def __init__(
        self,
        owner_class,
        **kwargs,
    ):
        self._subclass_attributes = set()
        fields = {}

        for name in dir(owner_class):
            attr = getattr(owner_class, name)
            if not isinstance(attr, Attribute):
                continue

            if not attr.name:
                attr.name = name
            fields[name] = attr

        self.fields = fields

        for v in self.fields.values():
            v.validators = {}
            for pname, pargs in v.plugins.items():
                if pname == 'enum':
                    v.validators[pname] = enum(pargs)

        for attr, value in kwargs.items():
            setattr(self, attr, value)
            self._subclass_attributes.add(attr)

        for base_class in owner_class.__bases__:
            parent_meta = getattr(base_class, 'meta', None)

            if isinstance(parent_meta, type(self)):
                for attr in parent_meta._subclass_attributes:
                    if hasattr(self, attr):
                        continue

                    setattr(self, attr, getattr(parent_meta, attr))


class Base:
    """ Base """

    meta = None
    _rehashed: set = None

    def __new__(cls, *arg, **kwarg):
        self = super().__new__(cls)
        self._rehashed = set()
        return self

    def __init__(
        self,
        arg_data: dict = None,
        **kwargs,
    ) -> None:
        if not arg_data:
            arg_data = kwargs

        # Coerce check

        need_self = []

        for name, fielddesc in self.meta.fields.items():
            try:
                if name in arg_data:
                    value = arg_data[name]
                elif getattr(self, name) is None:
                    value = fielddesc.default()

                setattr(self, name, value)

            except ErrorRequest:
                need_self.append(name)

        for name in need_self:
            fielddesc = self.meta.fields[name]

            if name in arg_data:
                value = arg_data[name]

            elif getattr(self, name) is None:
                try:
                    value = fielddesc.default()
                except ErrorRequest:
                    value = fielddesc.default(self=self, field=fielddesc)

            self.__dict__[name] = None
            setattr(self, name, value)

        #
        for k, v in arg_data.items():
            if not hasattr(self, k):
                continue

            if k in self.meta.fields:
                continue

            setattr(self, k, v)

        self.rehashed('-clean')

    def __init_subclass__(
        cls,
        meta_class=Meta,
        **kwargs,
    ):
        cls.meta = meta_class(
            cls,
            **kwargs,
        )

    def rehashed(self, *args, **kwargs):
        if not args and not kwargs:
            return copy.copy(self._rehashed)

        if len(args) == 1:
            name = args[0]

            if isinstance(name, dict):
                for k, v in name.items():
                    kwargs.setdefault(k, v)

                args = []

            else:
                if name == '-clean':
                    self._rehashed = set()
                    return None

                if name == '-check':
                    return copy.copy(self._rehashed)

                if isinstance(name, str):
                    if name not in self.meta.fields:
                        raise ErrorWrong(name)

                    return name in self._rehashed

                raise ErrorInvalid('rehashed')

        if len(args) % 2:
            raise ErrorInvalid('rehashed')

        for i in range(0, len(args), 2):
            kwargs.setdefault(args[i], args[i + 1])

        for name, rehashed in kwargs.items():
            if name not in self.meta.fields:
                continue

            if rehashed:
                self._rehashed.add(name)
            else:
                self._rehashed.discard(name)

        return None

    def rehash(self, *args, **kwargs):
        if len(args) == 1:
            row = args[0]

            if isinstance(row, dict):
                for name, value in row.items():
                    kwargs.setdefault(name, value)
                args = []

        if len(args) % 2:
            raise ErrorInvalid('rehash')

        for i in range(0, len(args), 2):
            kwargs.setdefault(args[i], args[i + 1])

        for name, value in kwargs.items():
            if name not in self.meta.fields:
                continue

            setattr(self, name, value)

    def json(self, **kwargs):
        """ Get dictionary of the object """

        res = {}

        for name in self.meta.fields:
            value = getattr(self, name)

            if hasattr(value, 'json'):
                value = value.json()

            res[name] = value

        for key, value in kwargs.items():
            res[key] = value

        return res

    def __repr__(self):
        return (
            f"Object {self.__class__.__name__}"
            f"({json.dumps(self.json(), ensure_ascii=False)})"
        )

    def __getitem__(self, key):
        if key not in self.meta.fields:
            raise ErrorWrong(str(key))
        return getattr(self, key)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            if hasattr(self, 'coerce'):
                coerce = getattr(self, 'coerce')
                other = coerce(other)
            elif isinstance(other, dict):
                try:
                    other = self.__class__(other)
                except ValueError:
                    return False
            else:
                return False

        if type(other) is not type(self):
            return False

        if id(self) == id(other):
            return True

        for name in self.meta.fields:
            if self[name] != other[name]:
                return False

        return True

    def items(self, by='rehashed'):
        if by == 'rehashed':
            for name in self.meta.fields:
                if self.rehashed(name):
                    yield name, getattr(self, name)

        elif by == 'all':
            for name in self.meta.fields:
                yield name, getattr(self, name)

        elif by == 'new':
            for name in self.meta.fields:
                if name in self.meta.table.pkey and getattr(self, name) is None:
                    continue
                yield name, getattr(self, name)

        else:
            raise ErrorWrong("by")


class Cursor(Base):
    """ Cursor """

    time = Attribute(types=int, required=True, default=lambda: int(time.time()))
    limit = Attribute(types=int)

    def __init__(self, row=None, **kw):
        if row is None:
            row = {}
        elif isinstance(row, Cursor):
            row = row.json()
        else:
            row = copy.copy(row)

        if isinstance(row, str):
            data = unpack(TOKEN, row)

            if data is None:
                row = {}
            elif isinstance(data, dict):
                row = data.get('cursor', {})
            else:
                row = {}

        elif row is None:
            row = {}

        self.list = []

        super().__init__(row, **kw)

    def __iter__(self):
        for item in self.list:
            yield item

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_traceback):
        pass

    @property
    def cursor_str(self):
        return pack(TOKEN, cursor=self)

    def is_full(self):
        return len(self.list) >= self.limit

    @staticmethod
    def _force_limit(limit):
        if limit is None:
            return CURSOR_LIMIT
        if limit > CURSOR_LIMIT:
            return CURSOR_LIMIT
        if limit < 1:
            return 1

        return limit


class BaseModel(Base):
    """ Base model """

    @property
    @abstractmethod
    def database(self):
        pass
    # @property
    # @abstractmethod
    # def _db(self):
    #     """ Database """
    #     return None

    # @property
    # @abstractmethod
    # def _name(self):
    #     """ Table name """
    #     return None

    def get_key(self, key=None):
        if key is None:
            key = self.meta.table.pkey

        if isinstance(key, (tuple, list)):
            return [getattr(self, x) for x in key]

        return [getattr(self, key)]

    @classmethod
    def get_db(cls, db=None):
        data = copy.copy(db)
        if data is None:
            data = {}

        if cls.database and 'db' not in data:
            data = {
                **data,
                'db': cls.database,
            }

        return data

    @classmethod
    def sqlbase(cls):
        paths = ['model']
        name = re.sub(r'([A-Z])', r'_\1', cls.__name__)
        if name.startswith('_'):
            name = name[1:]

        paths.append(name.lower())

        return os.path.join(*paths)

    @classmethod
    def sqlpath(cls, subpath):
        if not re.search(r'\.sql$', subpath):
            subpath += '.sqlt'
        return os.path.join(cls.sqlbase(), subpath)

    async def save(self, db=None, **kw):
        db = self.get_db(db)

        for k, v in self.meta.fields.items():
            if 'db_vars' in v.tags:
                value = getattr(self, k)

                if hasattr(value, 'rehashed'):
                    if value.rehashed():
                        self.rehashed(name=True)

        sql, args = sqlt('save.sqlt', {
            **kw,
            'key_def': 'id',
            'key_tuple': self.get_key(),
            'table': self.meta.table,
            'this': self,
            'sqlbase': self.sqlbase(),
            'shard': db.get('shard'),
        })

        print(sql, args)

        async with dbh(**db) as conn:
            data = await conn.fetchrow(sql, *args)

        print(data)

        if not data:
            raise Exception('Save exception')

        for k, v in data.items():
            if k not in self.meta.fields:
                continue

            setattr(self, k, v)

        self.rehashed('-clean')
        return self

    async def rm(self, db=None, **kw):
        """ Remove """

        db = self.get_db(db)

        sql, args = sqlt('rm.sqlt', {
            **kw,
            'key_def': ['id'],
            'key_tuple': self.get_key(),
            'table': self.meta.table,
            'this': self,
            'sqlbase': self.sqlbase(),
            'shard': db.get('shard'),
        })

        async with dbh(**db) as conn:
            data = await conn.fetchrow(sql, *args)

        if not data:
            raise Exception('Remove exception')

        for k, v in data.items():
            if k not in self.meta.fields:
                continue

            setattr(self, k, v)

        self.rehashed('-clean')
        return self

    @classmethod
    async def get(cls, ids=None, db=None, cursor=None, **kw):
        """ Get instances of the object """

        db = cls.get_db(db)

        if ids:
            kw = {
                **kw,
                'key_def': ('id',),
                'key': ids,
                'key_tuple': ids if isinstance(ids, (list, tuple)) else [ids],
                'class': cls,
                'table': cls.meta.table,
                'sqlbase': cls.sqlbase(),
                'shard': db.get('shard'),
            }

        else:
            kw = {
                **kw,
                'table': cls.meta.table,
                'sqlbase': cls.sqlbase(),
                'shard': db.get('shard'),
            }

            if 'sort' in kw and isinstance(kw['sort'], str):
                kw['sort'] = [kw['sort']]

            cursor = Cursor(kw)
            kw['cursor'] = cursor

        sql, args = sqlt('load.sqlt' if ids else 'list.sqlt', kw)

        async with dbh(**db) as conn:
            data = await conn.fetch(sql, *args)

        if ids:
            if not data:
                return None

            data = cls(data[0])
            if isinstance(db, dict) and 'shard' in db:
                data.actual_shard = db['shard']

            return data

        cursor.list = [cls(x) for x in data]

        if isinstance(db, dict) and 'shard' in db:
            for item in cursor.list:
                item.actual_shard = db['shard']

        return cursor.list, cursor.cursor_str

    async def reload(self, **kw):
        """ Update the instance according to the data from the DB

        After calling this function, all unsaved instance data will be erased
        """

        data = await self.get(self.get_key(), **kw)
        self.rehash(**dict(data.items('all')))
        self.rehashed('-clean')
        return self
