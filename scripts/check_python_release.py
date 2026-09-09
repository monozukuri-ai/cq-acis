"""Release metadata/archive checks, including safe retries of partial uploads."""
from __future__ import annotations

import argparse
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import tarfile
import tomllib
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def project_version() -> str:
    return tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']


def check_tag(tag: str, version: str) -> None:
    if tag and tag != f'v{version}':
        raise ValueError(f'Release tag {tag!r} must match Python version v{version}')


def metadata(data: bytes, version: str) -> None:
    parsed = BytesParser().parsebytes(data)
    if parsed['Name'] != 'cq-acis' or parsed['Version'] != version:
        raise ValueError('Artifact name/version does not match pyproject.toml')


def check_archives(directory: Path, version: str, wheels: int, sdists: int) -> dict[str, str]:
    wheel_paths = sorted(directory.glob('*.whl'))
    source_paths = sorted(directory.glob('*.tar.gz'))
    if len(wheel_paths) != wheels or len(source_paths) != sdists:
        raise ValueError(f'Expected {wheels} wheels and {sdists} sdists; found {len(wheel_paths)} and {len(source_paths)}')
    files = wheel_paths + source_paths
    if set(directory.iterdir()) != set(files):
        raise ValueError('Unexpected files in release artifact directory')
    for path in files:
        if path.suffix == '.whl':
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                if '-cp310-abi3-' not in path.name:
                    raise ValueError(f'Expected a Python 3.10 ABI3 wheel: {path.name}')
                if not any(n.startswith('cq_acis/_native.') and n.endswith(('.so', '.pyd')) for n in names):
                    raise ValueError('Wheel is missing the native extension')
                meta = [n for n in names if n.endswith('.dist-info/METADATA')]
                if len(meta) != 1:
                    raise ValueError('Expected one wheel metadata file')
                metadata(archive.read(meta[0]), version)
        else:
            with tarfile.open(path) as archive:
                names = archive.getnames()
                prefix = f'cq_acis-{version}/'
                required = ['pyproject.toml', 'Cargo.lock', 'crates/acis-core/src/sab.rs',
                            'crates/cq-acis-py/src/lib.rs', 'src/cq_acis/__init__.py', 'PKG-INFO']
                if any(prefix + member not in names for member in required):
                    raise ValueError('Source distribution is missing a required build input')
                member = archive.extractfile(prefix + 'PKG-INFO')
                if member is None:
                    raise ValueError('Missing sdist metadata')
                metadata(member.read(), version)
        leaked = any(part in {'corpus', '.venv', 'target', '.git'} for name in names for part in Path(name).parts)
        if path.suffix == '.whl':
            leaked |= any('tests' in Path(name).parts for name in names)
        else:
            # Rust crate tests are valid cargo source inputs; exclude the root
            # Python development suite and its public corpus from distributions.
            leaked |= any(len(Path(name).parts) > 1 and Path(name).parts[1] == 'tests' for name in names)
        if leaked:
            raise ValueError(f'Development files leaked into {path.name}')
        for suffix in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'licenses/ezdxf-MIT.txt', 'licenses/cadmpeg-Apache-2.0.txt'):
            if not any(n == suffix or n.endswith('/' + suffix) for n in names):
                raise ValueError(f'{path.name} is missing {suffix}')
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}


def check_existing(local: dict[str, str], remote: list[dict]) -> None:
    # Only identical subsets may be resumed. Never mix a previous implementation
    # or silently skip a filename containing different bytes.
    for item in remote:
        name = item['filename']
        if name not in local or item['digests']['sha256'] != local[name]:
            raise ValueError(f'PyPI already contains a different release artifact: {name}. Choose a new Python version.')


def check_pypi(version: str, files: dict[str, str]) -> None:
    url = f'https://pypi.org/pypi/cq-acis/{quote(version, safe="")}/json'
    try:
        with urlopen(url, timeout=30) as response:
            published = json.load(response)
    except HTTPError as error:
        if error.code == 404:
            print(f'PyPI version {version} is unused')
            return
        raise
    check_existing(files, published['urls'])
    print('Existing PyPI artifacts are identical; a partial upload can be resumed')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', default='')
    parser.add_argument('--dist', type=Path)
    parser.add_argument('--wheels', type=int, default=1)
    parser.add_argument('--sdists', type=int, default=0)
    parser.add_argument('--check-pypi', action='store_true')
    args = parser.parse_args()
    version = project_version()
    check_tag(args.tag, version)
    if args.dist:
        files = check_archives(args.dist, version, args.wheels, args.sdists)
        print(json.dumps(files, indent=2))
        if args.check_pypi:
            check_pypi(version, files)
    elif args.check_pypi:
        parser.error('--check-pypi requires --dist')
    print(f'Python release checks passed for {version}')


if __name__ == '__main__':
    main()
