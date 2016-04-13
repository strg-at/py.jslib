# Copyright © 2015 STRG.AT GmbH, Vienna, Austria
#
# This file is part of the The SCORE Framework.
#
# The SCORE Framework and all its parts are free software: you can redistribute
# them and/or modify them under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation which is in the
# file named COPYING.LESSER.txt.
#
# The SCORE Framework and all its parts are distributed without any WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. For more details see the GNU Lesser General Public
# License.
#
# If you have not received a copy of the GNU Lesser General Public License see
# http://www.gnu.org/licenses/.
#
# The License-Agreement realised between you as Licensee and STRG.AT GmbH as
# Licenser including the issue of its valid conclusion and its pre- and
# post-contractual effects is governed by the laws of Austria. Any disputes
# concerning this License-Agreement including the issue of its valid conclusion
# and its pre- and post-contractual effects are exclusively decided by the
# competent court, in whose district STRG.AT GmbH has its registered seat, at
# the discretion of STRG.AT GmbH also the competent court, in whose district the
# Licensee has his registered seat, an establishment or assets.

from score.init import ConfiguredModule
import urllib.request
import json
import os
from tarfile import TarFile
from io import BytesIO
import slimit.parser
import slimit.ast
from slimit.visitors.nodevisitor import ASTVisitor
import re
import tempfile
import time


defaults = {
    'cachedir': '__auto__',
    'rootdir': 'lib',
}


def init(confdict, js=None):
    """
    Initializes this module acoording to the :ref:`SCORE module initialization
    guidelines <module_initialization>` with the following configuration keys:
    """
    conf = defaults.copy()
    conf.update(confdict)
    cachedir = None
    if conf['cachedir'] == '__auto__':
        pass
    elif conf['cachedir'] != 'None':
        cachedir = conf['cachedir']
    if js:
        def traverse():
            prefix = conf['rootdir'] + '/'
            virtuals = js.virtfiles.paths()
            for path in js.paths():
                if path in virtuals:
                    continue
                if not path.startswith(prefix):
                    continue
                yield path[len(prefix):]
        rootdir = js.rootdir
    else:
        def traverse():
            for (path, dirnames, filenames) in os.walk(rootdir):
                for file in filenames:
                    if file.endswith('.js'):
                        yield os.path.join(path, file)
        rootdir = '.'
    if conf['rootdir']:
        rootdir = os.path.join(rootdir, conf['rootdir'])
    return ConfiguredScoreJslibModule(rootdir, traverse, cachedir)


class ConfiguredScoreJslibModule(ConfiguredModule):

    def __init__(self, rootdir, traverse, cachedir):
        import score.jslib
        super().__init__(score.jslib)
        self.rootdir = rootdir
        self.traverse = traverse
        self.cachedir = cachedir

    def list(self):
        return list(self)

    def __iter__(self):
        regex = re.compile(
            r'^//\s+(?P<name>[^@]+)@(?P<version>[^\s]+)\s+(?P<define>.*)$')
        for path in self.traverse():
            file = os.path.join(self.rootdir, path)
            firstline = open(file).readline()
            match = regex.match(firstline)
            if match:
                yield Library(
                    self,
                    match.group('name'),
                    path,
                    match.group('define'),
                    match.group('version'),
                )

    def install(self, library, path, define):
        meta = self.get_package_json(library)
        tarball_url = meta['dist']['tarball']
        tarball = TarFile.open(fileobj=BytesIO(
            urllib.request.urlopen(tarball_url).read()))
        main = self._find_main(meta, tarball)
        filepath = os.path.join(self.rootdir, path)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        file = open(filepath, 'w')
        file.write('// %s@%s %s\n' % (library, meta['version'], define))
        content = str(main.read(), 'UTF-8')
        if define:
            content = DefineAdjuster(define, content).replace_content()
        file.write(content)

    def get(self, name):
        if isinstance(name, Library):
            return name
        for library in self:
            if library.name == name:
                return library
        raise NotInstalled(library)

    def get_package_json(self, name):
        if isinstance(name, Library):
            name = name.name
        localdir = os.path.join(tempfile.gettempdir(), 'score', 'jslib')
        local = os.path.join(localdir, '%s.meta.json' % name)
        try:
            if time.time() - os.path.getmtime(local) < 300:
                return json.loads(open(local).read())
        except FileNotFoundError:
            pass
        meta_url = "http://registry.npmjs.org/%s/latest" % name
        content = str(urllib.request.urlopen(meta_url).read(), 'UTF-8')
        os.makedirs(localdir, exist_ok=True)
        open(local, 'w').write(content)
        return json.loads(content)

    def _find_main(self, meta, tarball):
        path = meta.get('browser')
        if not path:
            path = meta.get('main')
        if not path:
            file = tarball.extractfile(os.path.join('package', 'bower.json'))
            bower_meta = json.loads(str(file.read(), 'UTF-8'))
            path = bower_meta.get('main')
            if not path:
                path = bower_meta['browser']
        path = os.path.normpath(path)
        if path.endswith('.min.js') or path.endswith('-min.js'):
            test = path[:-7] + '.js'
            try:
                return tarball.extractfile(os.path.join('package', test))
            except KeyError:
                pass
        return tarball.extractfile(os.path.join('package', path))


class Library:

    def __init__(self, conf, name, path, define, version):
        self._conf = conf
        self.name = name
        self.path = path
        self.define = define
        self.version = version
        self._newest_version = None

    @property
    def newest_version(self):
        if not self._newest_version:
            self._newest_version = self._conf.get_package_json(self)['version']
        return self._newest_version

    @property
    def realpath(self):
        return os.path.join(self._conf.rootdir, self.path)


class Parser(slimit.parser.Parser):

    def p_identifier(self, p):
        """identifier : ID"""
        slimit.parser.Parser.p_identifier(self, p)
        p[0].lexpos = p.slice[1].lexpos


class DefineAdjuster(ASTVisitor):

    def __init__(self, name, content):
        self.name = name
        self.content = content
        self.start = None
        self.replace = None

    def replace_content(self):
        parser = Parser()
        open('/tmp/test.js', 'w').write(self.content)
        tree = parser.parse(self.content)
        self.visit(tree)
        if self.start is None:
            raise Exception('Could not find call to define()')
        lexer = slimit.lexer.Lexer()
        lexer.input(self.content)
        for token in lexer:
            if token.lexpos <= self.start:
                continue
            if not self.replace:
                if token.value != '(':
                    continue
                return self.content[:token.lexpos + 1] + \
                    ('"%s",' % self.name) + \
                    self.content[token.lexpos + 1:]
            if token.type == 'STRING' or token.type == 'ID':
                return self.content[:token.lexpos] + \
                    ('"%s",' % self.name) + \
                    self.content[token.lexpos + len(token.value) + 1:]
        return self.content

    def visit_FunctionCall(self, node):
        if getattr(node.identifier, 'value', None) == 'define':
            self.start = node.identifier.lexpos
            if len(node.args) == 3:
                self.replace = node.args[0]
        self.generic_visit(node)


class NotInstalled(Exception):
    """
    Raised when a library is requested, which is not installed.
    """
