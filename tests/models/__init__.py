from consql import make_base, Attribute, Table


Base = make_base('localhost:5432', 'main', 'postgres', 'password')
