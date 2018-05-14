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


SUPPORTED_CONF_FILES = ('.editorconfig', '.isort.cfg', 'setup.cfg', 'tox.ini')
THIRD_PARTY_RE = re.compile(r'^known_third_party(\s*)=(\s*?)[^\s]*$', re.M)


class Visitor(ast.NodeVisitor):
    def __init__(self):
        self.third_party = set()

    def _maybe_append_name(self, name):
        name, _, _ = name.partition('.')
        if classify_import(name) == ImportType.THIRD_PARTY:
            self.third_party.add(name)

    def visit_Import(self, node):
        for name in node.names:
            self._maybe_append_name(name.name)

    def visit_ImportFrom(self, node):
        if not node.level:
            self._maybe_append_name(node.module)


def third_party_imports(filenames):
    visitor = Visitor()
    for filename in filenames:
        with open(filename, 'rb') as f:
            visitor.visit(ast.parse(f.read()))
    return visitor.third_party


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--extra', action='append', default=[])
    args = parser.parse_args(argv)

    cmd = ('git', 'ls-files', '--', '*.py')
    filenames = subprocess.check_output(cmd).decode('UTF-8').splitlines()
    filenames.extend(args.extra)

    third_party = ','.join(sorted(third_party_imports(filenames)))

    for filename in SUPPORTED_CONF_FILES:
        if not os.path.exists(filename):
            continue

        with io.open(filename, encoding='UTF-8') as f:
            contents = f.read()

        if THIRD_PARTY_RE.search(contents):
            replacement = r'known_third_party\1=\2{}'.format(third_party)
            contents = THIRD_PARTY_RE.sub(replacement, contents)
            with io.open(filename, 'w', encoding='UTF-8') as f:
                f.write(contents)
            break
    else:
        print(
            'Creating an .isort.cfg with a known_third_party imports setting. '
            'Feel free to move the setting to a different config file in one '
            'of {}...'.format(', '.format(SUPPORTED_CONF_FILES)),
        )

        with io.open('.isort.cfg', 'a', encoding='UTF-8') as f:
            f.write('[settings]\nknown_third_party = {}\n'.format(third_party))


if __name__ == '__main__':
    exit(main())
