from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import argparse
import ast
import io
import os.path
import re
import subprocess

from aspy.refactor_imports.classify import classify_import
from aspy.refactor_imports.classify import ImportType


ENV_BLACKLIST = frozenset(('GIT_LITERAL_PATHSPECS', 'GIT_GLOB_PATHSPECS'))
SUPPORTED_CONF_FILES = ('.editorconfig', '.isort.cfg', 'setup.cfg', 'tox.ini')
THIRD_PARTY_RE = re.compile(r'^known_third_party(\s*)=(\s*?)[^\s]*$', re.M)
STDLIB_RE = re.compile(r'^known_standard_library(\s*)=(\s*?)([^\s]*$)', re.M)


class Visitor(ast.NodeVisitor):
    def __init__(self, appdirs=('.',)):
        self.appdirs = appdirs
        self.third_party = set()

    def _maybe_append_name(self, name):
        name, _, _ = name.partition('.')
        imp_type = classify_import(name, self.appdirs)
        if imp_type == ImportType.THIRD_PARTY:
            self.third_party.add(name)

    def visit_Import(self, node):
        for name in node.names:
            self._maybe_append_name(name.name)

    def visit_ImportFrom(self, node):
        if not node.level:
            self._maybe_append_name(node.module)


def third_party_imports(filenames, appdirs=('.',)):
    visitor = Visitor(appdirs)
    for filename in filenames:
        with open(filename, 'rb') as f:
            visitor.visit(ast.parse(f.read(), filename=filename))
    return visitor.third_party


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--extra', action='append', default=[])
    parser.add_argument('--exclude', default='^$')
    parser.add_argument(
        '--application-directories', default='.',
        help=(
            'Colon separated directories that are considered top-level '
            'application directories.  Defaults to `%(default)s`'
        ),
    )
    parser.add_argument(
        '--settings-path', default='.',
        help=(
            'Directory containing isort config file. '
            'Defaults to `%(default)s`'
        ),
    )
    args = parser.parse_args(argv)

    cmd = ('git', 'ls-files', '--', '*.py')
    env = {k: v for k, v in os.environ.items() if k not in ENV_BLACKLIST}
    out = subprocess.check_output(cmd, env=env).decode('UTF-8')
    filenames = out.splitlines() + args.extra

    exclude = re.compile(args.exclude)
    filenames = [f for f in filenames if not exclude.search(f)]

    appdirs = args.application_directories.split(':')
    collected_third_party = third_party_imports(filenames, appdirs)
    force_standard_library = set()

    for filename in SUPPORTED_CONF_FILES:
        filename = os.path.join(args.settings_path, filename)
        if not os.path.exists(filename):
            continue

        with io.open(filename, encoding='UTF-8') as f:
            contents = f.read()

        stdlib_match = next(STDLIB_RE.finditer(contents), None)
        if stdlib_match:
            stdlib_enumeration = stdlib_match.groups()[-1].replace(' ', '')
            force_standard_library = set(stdlib_enumeration.split(','))

        third_party = third_party_formatted(
            collected_third_party,
            force_standard_library,
        )
        if THIRD_PARTY_RE.search(contents):
            replacement = r'known_third_party\1=\2{}'.format(third_party)
            contents = THIRD_PARTY_RE.sub(replacement, contents)
            with io.open(filename, 'w', encoding='UTF-8') as f:
                f.write(contents)
            break
    else:
        third_party = third_party_formatted(
            collected_third_party,
            force_standard_library,
        )
        filename = os.path.join(args.settings_path, '.isort.cfg')
        if os.path.exists(filename):
            prefix = 'Updating'
            mode = 'a'
            contents = 'known_third_party = {}\n'.format(third_party)
        else:
            prefix = 'Creating'
            mode = 'w'
            contents = '[settings]\nknown_third_party = {}\n'.format(
                third_party,
            )

        print(
            '{} an .isort.cfg with a known_third_party setting. '
            'Feel free to move the setting to a different config file in '
            'one of {}...'.format(prefix, ', '.join(SUPPORTED_CONF_FILES)),
        )

        try:
            os.makedirs(args.settings_path)
        except OSError:
            if not os.path.isdir(args.settings_path):
                raise

        with io.open(filename, mode, encoding='UTF-8') as f:
            f.write(contents)


def third_party_formatted(collected_third_party, standard_library):
    filtered = [i for i in collected_third_party if i not in standard_library]
    return ','.join(sorted(filtered))


if __name__ == '__main__':
    exit(main())
