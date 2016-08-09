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

import click
import os


@click.group()
def main():
    """
    Manage your javascript libraries
    """


def output_missing_dependencies(jslib):
    missing = jslib.missing_dependencies()
    if not missing:
        return
    click.echo(
        'The following packages have unsatisfied dependencies:', err=True)
    for lib, dep, version in missing:
        click.echo(' - %s-%s requires %s%s' % (
            lib.name, lib.version, dep, version), err=True)


@main.command()
@click.argument('library')
@click.argument('define', required=False)
@click.pass_context
def install(clickctx, library, define=None):
    """
    Install a library.
    """
    jslib = clickctx.obj['conf'].load('jslib')
    lib = jslib.install(library, define)
    click.echo('Successfully installed %s-%s' % (lib.name, lib.version))
    output_missing_dependencies(jslib)


@main.command()
@click.option('-o', '--outdated', 'outdated_only', is_flag=True)
@click.option('-p', '--paths', is_flag=True)
@click.option('-d', '--defines', is_flag=True)
@click.pass_context
def list(clickctx, outdated_only, paths, defines):
    """
    Lists installed libraries.
    """
    jslib = clickctx.obj['conf'].load('jslib')
    for lib in jslib:
        if outdated_only and lib.version == lib.newest_version:
            continue
        output = '%s-%s' % (lib.name, lib.version)
        if defines:
            output += ' (%s)' % lib.define
        if paths:
            if lib.file:
                output += ' in %s' % os.path.relpath(lib.file)
            else:
                output += ' <virtual>'
        if outdated_only:
            output += ' -> %s' % lib.newest_version
        click.echo(output)
    output_missing_dependencies(jslib)


@main.command()
@click.argument('library')
@click.pass_context
def upgrade(clickctx, library):
    """
    Update an outdated library
    """
    jslib = clickctx.obj['conf'].load('jslib')
    lib = jslib.get(library)
    if lib.version == lib.newest_version:
        return
    jslib.install(lib.name, lib.define)
    output_missing_dependencies(jslib)


@main.command()
@click.option('-m', '--minify', is_flag=True)
@click.pass_context
def bundle(clickctx, minify):
    """
    Create a bundle with all files
    """
    score = clickctx.obj['conf'].load()
    with score.ctx.Context() as ctx:
        click.echo(score.jslib.make_bundle(ctx, minify=minify))
    output_missing_dependencies(score.jslib)


@main.command('dump-requirejs')
@click.pass_context
def dump_require(clickctx):
    """
    Create a bundle with all files
    """
    jslib = clickctx.obj['conf'].load('jslib')
    click.echo(jslib.render_requirejs())
    output_missing_dependencies(jslib)


@main.command('dump-requirejs-config')
@click.pass_context
def dump_require_config(clickctx):
    """
    Create a bundle with all files
    """
    score = clickctx.obj['conf'].load()
    with score.ctx.Context() as ctx:
        click.echo(score.jslib.render_requirejs_config(ctx))
    output_missing_dependencies(score.jslib)
