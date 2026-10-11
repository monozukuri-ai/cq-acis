"""Update the shared release version, exact workspace pins, and Cargo.lock.

Run `python scripts/bump_version.py <version> --offline` from the checkout.
Omit <version> to synchronize pins and the lockfile after editing only
[workspace.package].version in Cargo.toml. No tag or publication is created.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import tomllib

from check_python_release import project_version

ROOT = Path(__file__).resolve().parents[1]
STABLE_VERSION = re.compile(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)')


def update_manifest(text: str, version: str, dependencies: list[str]) -> str:
    """Preserve comments/formatting in the workspace's scalar and inline entries."""
    replacements = {('workspace.package', 'version'): ('', version)}
    replacements.update({('workspace.dependencies', name):
                         (r'\{[^\r\n}]*?\bversion\s*=\s*', f'={version}')
                         for name in dependencies})
    seen = set()
    section = ''
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        header = re.fullmatch(r'\s*\[([^\]]+)\]\s*(?:#.*)?', line)
        if header:
            section = header[1]
            continue
        for key, (prefix, value) in replacements.items():
            if key[0] != section:
                continue
            pattern = rf'^(\s*{re.escape(key[1])}\s*=\s*{prefix})([\"\']).*?\2'
            changed, count = re.subn(pattern, lambda m: f'{m[1]}{m[2]}{value}{m[2]}', line)
            if count:
                if key in seen:
                    raise ValueError(f'duplicate version field: {key}')
                seen.add(key)
                lines[index] = changed
                break
    if seen != replacements.keys():
        raise ValueError('unsupported Cargo.toml layout; expected scalar version and inline workspace dependencies')
    return ''.join(lines)


def bump_version(root: Path, version: str | None, *, offline: bool = False) -> str:
    manifest = root / 'Cargo.toml'
    lockfile = root / 'Cargo.lock'
    originals = {path: path.read_bytes() for path in (manifest, lockfile)}
    text = originals[manifest].decode('utf-8')
    workspace = tomllib.loads(text)['workspace']
    version = workspace['package']['version'] if version is None else version
    if not STABLE_VERSION.fullmatch(version):
        raise ValueError('version must be a stable X.Y.Z release without leading zeros')
    members = {(root / member).resolve() for member in workspace['members']}
    dependencies = [name for name, spec in workspace['dependencies'].items()
                    if isinstance(spec, dict) and 'path' in spec
                    and (root / spec['path']).resolve() in members]
    updated = update_manifest(text, version, dependencies)
    try:
        manifest.write_bytes(updated.encode('utf-8'))
        command = ['cargo', 'update', '--workspace']
        if offline:
            command.append('--offline')
        subprocess.run(command, cwd=root, check=True)
        project_version(root)
    except BaseException:
        for path, data in originals.items():
            path.write_bytes(data)
        raise
    return version


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version', nargs='?', help='new X.Y.Z version; defaults to workspace.package.version')
    parser.add_argument('--offline', action='store_true', help='update Cargo.lock without network access')
    args = parser.parse_args()
    try:
        version = bump_version(ROOT, args.version, offline=args.offline)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Version update failed: {error}\n')
    print(f'Workspace version {version}: Cargo.toml pins and Cargo.lock are synchronized')


if __name__ == '__main__':
    main()
