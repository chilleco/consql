import copy
import json
from abc import abstractmethod

from .errors import ErrorInvalid, ErrorWrong, ErrorRequest


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


class Attribute:
    """ Descriptor """

    name: str = None
    types = None
    default = None
    coerce = None
    always: bool = False
    required: bool = None
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

    @property
    @abstractmethod
    def database(self):
        pass

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
        plugins_namespace=None,
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
