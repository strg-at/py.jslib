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

from score.init import ConfiguredModule, ConfigurationError
import urllib.request
import json
import os
from tarfile import TarFile
from io import BytesIO
import re
import tempfile
import time


defaults = {
    'cachedir': '__auto__',
    'rootdir': None,
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
            virtuals = js.virtfiles.paths()
            yield from (path
                        for path in js.paths()
                        if path not in virtuals and path.startswith(prefix))
        prefix = ''
        rootdir = js.rootdir
        if conf['rootdir']:
            if not os.path.abspath(conf['rootdir']).startswith(rootdir):
                import score.jslib
                raise ConfigurationError(
                    score.jslib,
                    'Configured `rootdir` outside of score.js root')
            prefix = conf['rootdir'] + '/'
            rootdir = os.path.join(rootdir, conf['rootdir'])
    else:
        def traverse():
            for (path, dirnames, filenames) in os.walk(rootdir):
                for file in filenames:
                    if file.endswith('.js'):
                        yield os.path.join(path, file)
        rootdir = '.'
        if conf['rootdir']:
            if os.path.isabs(conf['rootdir']):
                rootdir = conf['rootdir']
            else:
                rootdir = os.path.join(rootdir, conf['rootdir'])
    return ConfiguredScoreJslibModule(js, rootdir, traverse, cachedir)


class ConfiguredScoreJslibModule(ConfiguredModule):

    def __init__(self, js, rootdir, traverse, cachedir):
        import score.jslib
        super().__init__(score.jslib)
        self.js = js
        self.rootdir = rootdir
        self.traverse = traverse
        self.cachedir = cachedir
        if js:
            self._register_virtjs()

    def _finalize(self, tpl=None):
        if tpl and 'html' in tpl.renderer.formats:
            tpl.renderer.add_function(
                'html', 'jslib', self._tags, escape_output=False)

    def _tags(self, ctx):
        return self.js._tags(ctx, '!require.js')

    def _register_virtjs(self):
        file = os.path.join(os.path.dirname(__file__), 'require.js')

        # TODO: enable hasher
        # def requirejs_hasher(ctx):
        #     # this is the version of requirejs we're using
        #     return '2.2.0'

        @self.js.virtjs('!require.js')  # , requirejs_hasher)
        def requirejs(ctx):
            return open(file).read() + self.generate_requirejs_config(ctx)

    def generate_require_map(self):
        libs = dict((lib.name, lib) for lib in self)
        result = {}
        for lib in libs.values():
            libdeps = {}
            if 'dependencies' not in lib.package_json:
                continue
            for dep in lib.package_json['dependencies']:
                if dep in libs:
                    libdeps[dep] = libs[dep].define
            if libdeps:
                result[lib.define] = libdeps
        return result

    def generate_requirejs_config(self, ctx):
        conf = {
            'map': self.generate_require_map(),
            # TODO: this should be the base path of self.js, if there is one
            'baseUrl': '/js/',
        }
        if not conf['map']:
            del conf['map']
        return 'require.config(%s);\n' % json.dumps(conf)

    def list(self):
        return list(self)

    def __iter__(self):
        regex = re.compile(
            r'^//\s+(?P<name>[^@]+)@(?P<version>[^\s]+)$')
        for path in self.traverse():
            file = os.path.join(self.rootdir, path)
            firstline = open(file).readline()
            match = regex.match(firstline)
            if match:
                yield Library(
                    self,
                    match.group('name'),
                    path,
                    match.group('version'),
                )

    def install(self, library, path):
        meta = self.get_package_json(library)
        tarball_url = meta['dist']['tarball']
        tarball = TarFile.open(fileobj=BytesIO(
            urllib.request.urlopen(tarball_url).read()))
        main = self._find_main(meta, tarball)
        filepath = os.path.join(self.rootdir, path)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        file = open(filepath, 'w')
        file.write('// %s@%s\n' % (library, meta['version']))
        content = str(main.read(), 'UTF-8')
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

    def __init__(self, conf, name, path, version):
        self._conf = conf
        self.name = name
        self.path = path
        self.version = version
        self._package_json = None

    @property
    def define(self):
        return self.path[:-3]

    @property
    def newest_version(self):
        return self.package_json['version']

    @property
    def package_json(self):
        if not self._package_json:
            self._package_json = self._conf.get_package_json(self)
        return self._package_json

    @property
    def file(self):
        return os.path.join(self._conf.rootdir, self.path)


class NotInstalled(Exception):
    """
    Raised when a library is requested, which is not installed.
    """
