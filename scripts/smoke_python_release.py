"""Install the built distribution in clean environments and exercise native CAD APIs."""
from __future__ import annotations

import argparse
import importlib.machinery
import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def installed_smoke(corpus: Path) -> None:
    print(f'Checking installed cq-acis {importlib.metadata.version("cq-acis")} on {sys.version}', flush=True)
    import cq_acis
    from cq_acis import _native, parse_sat_model, parse_sab_model, to_cadquery

    for module in (cq_acis, _native):
        path = Path(module.__file__).resolve()
        if not path.is_relative_to(Path(sys.prefix).resolve()):
            raise AssertionError(f'Imported checkout code instead of the installed wheel: {path}')
    assert any(_native.__file__.endswith(suffix) for suffix in importlib.machinery.EXTENSION_SUFFIXES)
    for filename, parse in [('cube_sat_700.sat', parse_sat_model), ('cube_asm_sab_22300.sab', parse_sab_model)]:
        model = parse((corpus / 'data/ezdxf' / filename).read_bytes())
        if isinstance(model, cq_acis.SatModel):
            model = model.as_acis_model()
        native = model.to_native()
        assert native.to_model() == model
        solid = to_cadquery(native).val()
        assert solid.isValid()
        assert (len(solid.Solids()), len(solid.Faces()), len(solid.Edges()), len(solid.Vertices())) == (1, 6, 12, 8)
        assert abs(solid.Volume() - 777**3) < 1e-3
    print('Native SAT/SAB/CadQuery assertions passed; checking interpreter shutdown', flush=True)


def clean_install(wheel: Path, interpreter: str) -> None:
    with tempfile.TemporaryDirectory(prefix='cq-acis-wheel-') as temporary:
        root = Path(temporary).resolve()
        environment = dict(os.environ)
        for name in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV'):
            environment.pop(name, None)
        subprocess.run([interpreter, '-m', 'venv', str(root / 'venv')], check=True, env=environment)
        python = root / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        # Select versions with published wheels (notably Numba/llvmlite on Intel
        # macOS) instead of attempting to build native dependencies from source.
        subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '--only-binary=:all:', str(wheel)], check=True, env=environment)
        subprocess.run([str(python), '-m', 'pip', 'check'], check=True, env=environment)
        subprocess.run([str(python), '-m', 'pip', 'list', '--format=freeze'], check=True, env=environment)
        subprocess.run([str(python), '-I', '-X', 'faulthandler', '-u', str(Path(__file__).resolve()), '--installed', '--corpus', str(ROOT / 'corpus')], cwd=root, check=True, env=environment)
        # Native dependencies can crash after all assertions pass. Only the
        # parent can confirm that interpreter shutdown also succeeded.
        print(f'Wheel smoke passed, including interpreter shutdown ({interpreter})', flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path)
    parser.add_argument('--python', action='append', default=[])
    parser.add_argument('--sdist', action='store_true', help='Rebuild the sdist before installing its wheel')
    parser.add_argument('--installed', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--corpus', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.installed:
        installed_smoke(args.corpus)
        return
    if args.dist is None:
        parser.error('--dist is required')
    interpreters = args.python or [sys.executable]
    if args.sdist:
        sources = list(args.dist.resolve().glob('*.tar.gz'))
        if len(sources) != 1:
            parser.error('Expected exactly one sdist')
        with tempfile.TemporaryDirectory(prefix='cq-acis-sdist-') as temporary:
            root = Path(temporary)
            with tarfile.open(sources[0]) as archive:
                archive.extractall(root, filter='data')
            projects = list(root.glob('*/pyproject.toml'))
            if len(projects) != 1:
                raise ValueError('Expected one extracted source project')
            output = root / 'wheel'
            subprocess.run([sys.executable, '-m', 'maturin', 'build', '--release', '--locked', '--out', str(output), '--interpreter', sys.executable], cwd=projects[0].parent, check=True)
            wheels = list(output.glob('*.whl'))
            if len(wheels) != 1:
                raise ValueError('Expected one rebuilt wheel')
            for interpreter in interpreters:
                clean_install(wheels[0], interpreter)
    else:
        wheels = list(args.dist.resolve().glob('*.whl'))
        if len(wheels) != 1:
            parser.error('Expected exactly one platform wheel')
        for interpreter in interpreters:
            clean_install(wheels[0], interpreter)


if __name__ == '__main__':
    main()
