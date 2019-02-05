#!/usr/bin/env python3
"""
Custom python file cleaning:
* remove trailing white space to satisfy flake8
"""
import re
from pathlib import Path

trailing_white = re.compile(b' +\n')


def clean_file(p: Path):
    content = p.read_bytes()
    content, changes = trailing_white.subn(b'\n', content)
    if changes:
        p.write_bytes(content)
        print(f'{p}: {changes} lines cleaned')
        return True


def main():
    files = 0
    files_changed = 0
    root_dir = Path(__file__).parent.parent
    for path in (root_dir / 'em2', root_dir / 'tests'):
        for file in path.glob('**/*.py'):
            files += 1
            changes = clean_file(file)
            if changes:
                files_changed += 1

    if files_changed:
        print(
            f'clean-python: \x1b[1m{files_changed} file{"s" if files_changed > 1 else ""} cleaned\x1b[0m, '
            f'{files - files_changed} files left unchanged.'
        )
    else:
        print(f'clean-python: {files - files_changed} files left unchanged.')


if __name__ == '__main__':
    main()
