import json
from abc import abstractmethod

from .errors import ErrorInvalid, ErrorRequest


class Attribute:
    """ Descriptor """

    name: str = None
    types = None
    default = None
    coerce = None
    always: bool = False
    required: bool = None

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


class Base:
    """ Base """

    meta = None
    _rehashed: set = None

    @property
    @abstractmethod
    def database(self):
        pass

    def __init__(
        self,
        arg_data: dict = None,
        **kwargs,
    ) -> None:
        if not arg_data:
            arg_data = kwargs

        for k, v in arg_data.items():
            if not hasattr(self, k):
                continue
            if k in self.meta.fields:
                continue

            setattr(self, k, v)

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
