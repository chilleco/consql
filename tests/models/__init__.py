from consql import make_base, Attribute, Table, coerces


Base = make_base('localhost:5432', 'main', 'postgres', 'password')
