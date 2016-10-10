# Copyright © 2015,2016 STRG.AT GmbH, Vienna, Austria
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
import subprocess
import hashlib


defaults = {
    'cachedir': None,
    'rootdir': None,
    'urlbase': '/js/',
}


def init(confdict, js=None):
    """
    Initializes this module acoording to the :ref:`SCORE module initialization
    guidelines <module_initialization>` with the following configuration keys:
    """
    conf = defaults.copy()
    conf.update(confdict)
    if conf['cachedir']:
        cachedir = conf['cachedir']
        if not os.path.isdir(cachedir):
            import score.jslib
            raise ConfigurationError(
                score.jslib,
                'Configured `cachedir` does not exist')
    else:
        cachedir = os.path.join(tempfile.gettempdir(), 'score', 'jslib')
        os.makedirs(cachedir, exist_ok=True)
    rootdir = None
    if js:
        rootdir = js.rootdir
        if conf['rootdir']:
            if not os.path.abspath(conf['rootdir']).startswith(rootdir):
                import score.jslib
                raise ConfigurationError(
                    score.jslib,
                    'Configured `rootdir` outside of score.js root')
            rootdir = os.path.join(js.rootdir, conf['rootdir'])
    else:
        if conf['rootdir']:
            if not os.path.isdir(conf['rootdir']):
                import score.jslib
                raise ConfigurationError(
                    score.jslib, 'Configured `rootdir` does not exit')
            rootdir = conf['rootdir']
        else:
            import score.jslib
            raise ConfigurationError(
                score.jslib, 'No `rootdir` configured')
    return ConfiguredScoreJslibModule(js, rootdir, cachedir, conf['urlbase'])


class ConfiguredScoreJslibModule(ConfiguredModule):

    def __init__(self, js, rootdir, cachedir, urlbase):
        import score.jslib
        super().__init__(score.jslib)
        self.js = js
        self.rootdir = rootdir
        self.cachedir = cachedir
        self.virtlibs = []
        self.urlbase = urlbase
        if js:
            self._register_requirejs_virtjs()
            self._register_almond_virtjs()
            self._register_bundle_virtjs()

    def virtlib(self, define, version, dependencies):
        def wrap(func):
            self.virtlibs.append(VirtualLibrary(
                self, define, define + '.js', version, dependencies))
            self.js.virtjs(define + '.js')(func)
            return func
        return wrap

    def traverse(self):
        if self.js:
            if self.rootdir != self.js.rootdir:
                prefix = os.path.relpath(self.rootdir, self.js.rootdir) + '/'
                yield from (path
                            for path in self.js.paths()
                            if path != '!require.js' and
                            path.startswith(prefix))
            else:
                yield from (path
                            for path in self.js.paths()
                            if path != '!require.js')
        else:
            for (path, dirnames, filenames) in os.walk(self.rootdir):
                for file in filenames:
                    if file.endswith('.js'):
                        yield os.path.relpath(os.path.join(path, file),
                                              self.rootdir)

    def _finalize(self, tpl=None):
        if tpl and 'html' in tpl.renderer.formats:
            tpl.renderer.add_function(
                'html', 'jslib', self._tags, escape_output=False)

    def _tags(self, ctx):
        if self.js.combine:
            return self.js._tags(ctx, '_require_bundle.js')
        else:
            paths = list(self.js.virtfiles.paths())
            paths.remove('!require.js')
            paths.remove('_almond.js')
            paths.remove('_require_bundle.js')
            paths.insert(0, '!require.js')
            for virtlib in self.virtlibs:
                try:
                    paths.remove(virtlib.define + '.js')
                except ValueError:
                    pass
            return self.js._tags(ctx, *paths)

    def _register_requirejs_virtjs(self):
        @self.js.virtjs('!require.js')
        def requirejs(ctx):
            return (self.render_requirejs() +
                    self.render_requirejs_config(ctx))

    def _register_almond_virtjs(self):
        @self.js.virtjs('_almond.js')
        def requirejs(ctx):
            return (self.render_almondjs() +
                    self.render_requirejs_config(ctx))

    def render_requirejs(self):
        file = os.path.join(os.path.dirname(__file__), 'require.js')
        return open(file).read()

    def render_almondjs(self):
        file = os.path.join(os.path.dirname(__file__), 'almond.js')
        return open(file).read()

    def render_requirejs_config(self, ctx):
        conf = {
            'map': self._render_require_map(),
            'baseUrl': self.urlbase,
        }
        if not conf['map']:
            del conf['map']
        return 'require.config(%s);\n' % json.dumps(conf)

    def missing_dependencies(self):
        missing = []
        libs = dict((lib.name, lib) for lib in self)
        for lib in libs.values():
            dependencies = lib.dependencies
            for dep in dependencies:
                if dep not in libs:
                    missing.append((lib, dep, dependencies[dep]))
        return missing

    def _render_require_map(self):
        libs = dict((lib.name, lib) for lib in self)
        result = {}
        for lib in libs.values():
            libdeps = {}
            for dep in lib.dependencies:
                if dep in libs and dep != libs[dep].define:
                    libdeps[dep] = libs[dep].define
            if libdeps:
                result[lib.define] = libdeps
        return result

    def _register_bundle_virtjs(self):

        def bundle_hash(ctx):
            hashes = map(lambda h: h(), self.js.generate_combined_hasher(ctx))
            return hashlib.sha256(''.join(hashes).encode('UTF-8')).hexdigest()

        @self.js.virtjs('_require_bundle.js', bundle_hash)
        def requirejs_bundle(ctx):
            return self.make_bundle(ctx, minify=self.js.minify)

    def list(self):
        return list(self)

    def __iter__(self):
        regex = re.compile(
            r'^//\s+(?P<name>[^@]+)@(?P<version>[^\s]+)$')
        for path in self.traverse():
            file = os.path.join(self.rootdir, path)
            try:
                firstline = open(file).readline()
            except FileNotFoundError:
                continue
            match = regex.match(firstline)
            if match:
                yield Library(
                    self,
                    match.group('name'),
                    path,
                    match.group('version'),
                )
        yield from self.virtlibs

    def make_bundle(self, ctx, minify=True):
        files = ['_almond.js']
        names = [None]
        contents = [self.render_requirejs()]
        replaceExisting = [False]
        for path in self.traverse():
            files.append(path)
            if self.js:
                contents.append(self.js.tpl.renderer.render_file(ctx, path))
            else:
                filepath = os.path.join(self.rootdir, path)
                contents.append(open(filepath).read())
            names.append(re.sub(r'\.js(\..+)?$', '', path))
            replaceExisting.append(False)
        file = os.path.join(os.path.dirname(__file__), 'rewrite.js')
        script = open(file).read() % (
            json.dumps({'files': files, 'names': names,
                        'contents': contents, 'minify': minify,
                        'replaceExisting': replaceExisting}))
        process = subprocess.Popen(['node'],
                                   stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(script.encode('UTF-8'))
        stdout, stderr = str(stdout, 'UTF-8'), str(stderr, 'UTF-8')
        if process.returncode:
            self.log.error(stderr)
            try:
                raise subprocess.CalledProcessError(
                    process.returncode, 'node', output=stdout, stderr=stderr)
            except TypeError:
                # the stderr kwarg is only available in python 3.5
                pass
            raise subprocess.CalledProcessError(
                process.returncode, 'node', output=stderr)
        for line in stderr.split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.startswith('WARN: '):
                line = line[6:]
            self.log.info(line)
        return (stdout + self.render_requirejs_config(ctx))

    def install(self, library, define=None):
        if not define:
            define = library
        meta = self.get_package_json(library)
        tarball_url = meta['dist']['tarball']
        tarball = TarFile.open(fileobj=BytesIO(
            urllib.request.urlopen(tarball_url).read()))
        main = self._find_main(meta, tarball)
        filepath = os.path.join(self.rootdir, '%s.js' % define)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        file = open(filepath, 'w')
        file.write('// %s@%s\n' % (library, meta['version']))
        content = str(main.read(), 'UTF-8')
        file.write(content)
        return Library(self, library, define, meta['version'])

    def get(self, name):
        if isinstance(name, Library):
            return name
        for library in self:
            if library.name == name:
                return library
        raise NotInstalled(library)

    def get_package_json(self, name, version='latest'):
        if isinstance(name, Library):
            name = name.name
        local = os.path.join(self.cachedir, '%s-%s.meta.json' % (name, version))
        try:
            mtime = os.path.getmtime(local)
            if version != 'latest' or time.time() - mtime < 3600:
                return json.loads(open(local).read())
        except FileNotFoundError:
            pass
        meta_url = "http://registry.npmjs.org/%s/%s" % (name, version)
        content = str(urllib.request.urlopen(meta_url).read(), 'UTF-8')
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
    def dependencies(self):
        if 'dependencies' not in self.package_json:
            return []
        return self.package_json['dependencies']

    @property
    def newest_version(self):
        return self._conf.get_package_json(self.name)['version']

    @property
    def package_json(self):
        if not self._package_json:
            self._package_json = self._conf.get_package_json(
                self.name, self.version)
        return self._package_json

    @property
    def file(self):
        return os.path.join(self._conf.rootdir, self.path)


class VirtualLibrary(Library):

    def __init__(self, conf, name, path, version, dependencies):
        super().__init__(conf, name, path, version)
        self._dependencies = dependencies

    @property
    def dependencies(self):
        return self._dependencies

    @property
    def newest_version(self):
        return self.version

    @property
    def package_json(self):
        return {}

    @property
    def file(self):
        return None


class NotInstalled(Exception):
    """
    Raised when a library is requested, which is not installed.
    """
