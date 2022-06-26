"""
JSON handler
"""

# pylint: disable=super-with-arguments,too-many-function-args

import json
import datetime
import glob
import os
import os.path
import re
import sys
from threading import local

from libdev.cfg import cfg
import jinja2
import jinja2.ext
import jinja2.nodes


_bindValues = local()


class _BindSQLFragmentExtension(jinja2.ext.Extension):
    def __init__(self, env):
        super(_BindSQLFragmentExtension, self).__init__(env)
        env.filters['i'] = lambda x: _QuoteVariable(self, x, False)
        env.filters['q'] = lambda x: _QuoteVariable(self, x, True)
        env.filters['vlist'] = lambda x: _QuoteVlist(self, x)
        env.filters['j'] = lambda x: _QuoteJson(self, x)

    def parse(self, parser):
        raise RuntimeError('Something broken: parse is called')

    def filter_stream(self, stream):
        generator = self._generator(stream)
        return jinja2.lexer.TokenStream(generator,
                                        stream.name, stream.filename)

    @staticmethod
    def _generator(stream):
        for token in stream:
            if token.type == jinja2.lexer.TOKEN_VARIABLE_END:
                yield jinja2.lexer.Token(
                    token.lineno,
                    jinja2.lexer.TOKEN_RPAREN,
                    ")"
                )
                yield jinja2.lexer.Token(
                    token.lineno,
                    jinja2.lexer.TOKEN_PIPE,
                    "|"
                )
                yield jinja2.lexer.Token(
                    token.lineno,
                    jinja2.lexer.TOKEN_NAME,
                    'q'
                )
            yield token

            if token.type == jinja2.lexer.TOKEN_VARIABLE_BEGIN:
                yield jinja2.lexer.Token(
                    token.lineno,
                    jinja2.lexer.TOKEN_LPAREN,
                    "("
                )

class _QuoteJson():
    def __init__(self, ext, v):
        self.e = ext
        self.v = v

    def __str__(self):
        return self.escape()

    def escape(self):
        if isinstance(self.v, (_QuoteVariable, _QuoteVlist)):
            raise RuntimeError('Do not use |j and |q/|i filters together')

        _bindValues.lst.append(_bindValues.json_encoder(self.v))

        if _bindValues.placeholders == 'prepare':
            return '$%d' % (len(_bindValues.lst))

        return _bindValues.placeholders


class _QuoteVlist():
    def __init__(self, ext, v):
        self.e = ext

        if isinstance(v, int):
            self.v = (v,)
        elif isinstance(v, float):
            self.v = (v,)
        elif isinstance(v, str):
            self.v = (v,)
        else:
            self.v = v

    def __str__(self):
        return self.escape()

    def escape(self):
        res = ''
        for bv in self.v:
            if res:
                res = res + ','

            _bindValues.lst.append(bv)

            if _bindValues.placeholders == 'prepare':
                res += '$%d' % (len(_bindValues.lst))
            else:
                res += _bindValues.placeholders

        return res


class _QuoteVariable():
    def __init__(self, ext, v, quote=True):
        self.e = ext
        self.v = v
        self.q = quote

        while isinstance(self.v, _QuoteVariable):
            self.q = self.v.q
            self.v = self.v.v

    def __str__(self):
        return self.escape()

    def escape(self):
        if isinstance(self.v, (_QuoteVariable, _QuoteVlist, _QuoteJson)):
            return self.v.escape()

        if self.q:
            try:
                if hasattr(self.v, 'postgresql'):
                    v = self.v.postgresql()
                else:
                    v = self.v
            except:
                v = self.v

            _bindValues.lst.append(v)

            if _bindValues.placeholders == 'prepare':
                return '$%d' % (len(_bindValues.lst))

            return _bindValues.placeholders

        else:
            return str(self.v)

class agent():
    directory: str

    def __init__(
        self,
        directory='tsql',
        *,
        placeholders='prepare',
        json_encoder=None,
        loader=None,
    ):
        self.directory = directory

        if loader is None:
            loader = jinja2.FileSystemLoader(self.directory)

        self._env = jinja2.Environment(
            loader=loader,
            extensions=[
                _BindSQLFragmentExtension
            ],
        )
        self._env.filters['datetime'] = lambda i: datetime.datetime.strptime(i, '%Y-%m-%d %H:%M:%S')

        if json_encoder:
            self.json_encoder = json_encoder
        else:
            self.json_encoder = json.dumps

        self._cache = {}
        self.placeholders = placeholders

    def __call__(self, fname: str, args: dict = None):
        tpl = self._cache.get(fname)

        if not tpl:
            tpl = self._env.get_template(fname)
            self._cache[fname] = tpl

        return self._render(tpl, args)

    def _render(self, tpl, args: dict = None):
        if not args:
            args = {}

        try:
            _bindValues.lst = []
            _bindValues.placeholders = self.placeholders
            _bindValues.json_encoder = self.json_encoder

            res = tpl.render(**args)
            vlist = _bindValues.lst

        finally:
            del _bindValues.lst
            del _bindValues.placeholders
            del _bindValues.json_encoder

        return res, vlist

    def inline(self, sqlt: str, args: dict = None):
        return self._render(self._env.from_string(sqlt), args)

def _sql_variable_quote(v):
    if v is None:
        return 'NULL'

    if hasattr(v, 'postgresql'):
        v = v.postgresql()

    if isinstance(v, datetime.datetime):
        return v.strftime("'%F %T%z'")

    if isinstance(v, (int, float)):
        return str(v)

    if isinstance(v, (list, set, tuple)):
        sv = [_sql_variable_quote(x) for x in v]

        if sv:
            if sv[0].startswith("'"):
                suffix = '::TEXT[]'
            else:
                suffix = ''
        else:
            suffix = ''

        return f"ARRAY[{','.join(sv)}]{suffix}"

    return "'" + str(v) + "'"


def _sql_variable_inline(sql, bindvars):
    for i in range(len(bindvars), 0, -1):
        v = bindvars[i - 1]
        v = _sql_variable_quote(v)
        sql = sql.replace(f'${i}', v)

    return sql

class _sqlt_agent(agent):
    def __call__(self, name: str, args: dict=None):

        dump_str = cfg('pg.debug', '')
        if not dump_str:
            return super().__call__(name, args)

        dump_items = {
            i[0]: i[-1]
            for i in [
                j.split('=', 1)
                for j in dump_str.split(',')
            ]
        }

        fh = sys.stderr
        if 'stdout' in dump_items:
            fh = sys.stdout

        sql, bindvars = super().__call__(name, args)
        sqlp, bindvarsp = sql, bindvars

        if 'copy' in dump_items:
            dump_items['inline'] = 'inline'

        if 'inline' in dump_items:
            sqlp = _sql_variable_inline(sqlp, bindvarsp)
            bindvarsp = []

        if 'tag' in dump_items:
            if sql.find(dump_items['tag']) == -1:
                return super().__call__(name, args)

        print('# ', '=' * 77, file=fh, sep='')
        print('#    template:', name, file=fh)
        for n, value in args.items():
            print(f'#    argument: {n}={value}', file=fh)
        print('# ', '-' * 77, file=fh, sep='')

        print('#  result sql:')
        if 'copy' in dump_items:
            print(sqlp, file=fh)
        else:
            print(re.sub(r'^', '# ', sqlp, 0, re.RegexFlag.M), file=fh)
        if bindvarsp:
            for n, value in enumerate(bindvarsp):
                print(f'#  result var: ${n+1}={value}', file=fh)
        print('# ', '=' * 77, file=fh, sep='')

        return sql, bindvars

    def __init__(self):
        directory = os.path.join('.', cfg('pg.sqlt_path', 'tsql'))
        patterns = ['*.sqlt']
        files = []

        for pattern in patterns:
            pattern_files = glob.glob(
                os.path.join(directory, '**', pattern),
                recursive=True,
            )
            files.extend(pattern_files)

        self.cache = {}

        for file_name in files:
            if not os.path.isfile(file_name):
                continue

            key = os.path.relpath(file_name, start=directory)
            with open(file_name, 'r') as handle:
                self.cache[key] = handle.read()
                dot_key = os.path.join('.', key)
                self.cache[dot_key] = self.cache[key]

        super().__init__(
            directory,
            loader=jinja2.loaders.DictLoader(self.cache),
            json_encoder=json.dumps,
        )

        self._env.globals['match'] = self._match

    def template_exists(self, name):
        print(self.cache.keys())
        return name in self.cache

    @staticmethod
    def _match(value, regex):
        pattern = re.compile(regex)
        return pattern.match(value)


sqlt = _sqlt_agent()
