"""Install the built distribution in clean environments and exercise native CAD APIs.

Each interpreter gets one clean virtual environment per extra: ``cadquery``
(CadQuery shapes, Workplanes and authoring) and ``occt`` (bare OCCT shapes
through ``cadquery-ocp-novtk`` with no CadQuery installed).
"""
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
EXTRAS = ('cadquery', 'occt')


def _native_models(corpus: Path) -> list:
    import cq_acis
    from cq_acis import _native, parse_sat_model, parse_sab_model

    assert _native.CORE_VERSION == importlib.metadata.version('cq-acis')
    for module in (cq_acis, _native):
        path = Path(module.__file__).resolve()
        if not path.is_relative_to(Path(sys.prefix).resolve()):
            raise AssertionError(f'Imported checkout code instead of the installed wheel: {path}')
    assert any(_native.__file__.endswith(suffix) for suffix in importlib.machinery.EXTENSION_SUFFIXES)
    models = []
    for filename, parse in [('cube_sat_700.sat', parse_sat_model), ('cube_asm_sab_22300.sab', parse_sab_model)]:
        model = parse((corpus / 'data/ezdxf' / filename).read_bytes())
        if isinstance(model, cq_acis.SatModel):
            model = model.as_acis_model()
        native = model.to_native()
        assert native.to_model() == model
        models.append(native)
    return models


def _cadquery_smoke(models: list) -> None:
    from cq_acis import to_cadquery
    for native in models:
        solid = to_cadquery(native).val()
        assert solid.isValid()
        assert (len(solid.Solids()), len(solid.Faces()), len(solid.Edges()), len(solid.Vertices())) == (1, 6, 12, 8)
        assert abs(solid.Volume() - 777**3) < 1e-3
    print('Native SAT/SAB/CadQuery assertions passed; checking interpreter shutdown', flush=True)

    import cadquery as cq
    from cq_acis import from_cadquery, parse_sab_model
    solid = cq.Workplane('XY').circle(3).extrude(8).val()
    authored = from_cadquery(solid)
    spec = authored.to_spec()
    assert spec['faces'] and spec['edges'] and spec['vertices_mm']
    rebuilt = to_cadquery(parse_sab_model(authored.to_sab())).val()
    assert rebuilt.isValid() and len(rebuilt.Solids()) == 1
    assert abs(rebuilt.Volume() - solid.Volume()) < 1e-7
    assert authored.native_qualified is False


def _occt_smoke(models: list) -> None:
    try:
        import cadquery  # noqa: F401
    except ImportError:
        pass
    else:
        raise AssertionError('the occt smoke must run in an environment without cadquery')
    from OCP.TopoDS import TopoDS_Shape
    from cq_acis import CadQueryConverter, CadQueryDependencyError, convert_model_occt, to_cadquery
    from cq_acis._occt_shapes import Shape
    for native in models:
        converter = CadQueryConverter(native)
        assert converter.backend == 'occt', converter.backend
        shapes = convert_model_occt(native)
        assert len(shapes) == 1 and isinstance(shapes[0], TopoDS_Shape)
        solid = Shape.cast(shapes[0])
        assert solid.isValid()
        assert (len(solid.Solids()), len(solid.Faces()), len(solid.Edges()), len(solid.Vertices())) == (1, 6, 12, 8)
        assert abs(solid.Volume() - 777**3) < 1e-3
        try:
            to_cadquery(native)
        except CadQueryDependencyError as error:
            assert 'cq-acis[cadquery]' in str(error), error
        else:
            raise AssertionError('to_cadquery must require CadQuery')
    print('Native SAT/SAB/OCCT assertions passed; checking interpreter shutdown', flush=True)


def installed_smoke(corpus: Path, extra: str = 'cadquery') -> None:
    print(f'Checking installed cq-acis[{extra}] {importlib.metadata.version("cq-acis")} on {sys.version}', flush=True)
    models = _native_models(corpus)
    if extra == 'cadquery':
        _cadquery_smoke(models)
    elif extra == 'occt':
        _occt_smoke(models)
    else:
        raise ValueError(f'unknown extra {extra!r}')


def clean_install(wheel: Path, interpreter: str, extra: str = 'cadquery') -> None:
    with tempfile.TemporaryDirectory(prefix='cq-acis-wheel-') as temporary:
        root = Path(temporary).resolve()
        environment = dict(os.environ)
        for name in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV'):
            environment.pop(name, None)
        subprocess.run([interpreter, '-m', 'venv', str(root / 'venv')], check=True, env=environment)
        python = root / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        # Select versions with published wheels (notably Numba/llvmlite on Intel
        # macOS) instead of attempting to build native dependencies from source.
        subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '--only-binary=:all:', f'{wheel}[{extra}]'], check=True, env=environment)
        subprocess.run([str(python), '-m', 'pip', 'check'], check=True, env=environment)
        subprocess.run([str(python), '-m', 'pip', 'list', '--format=freeze'], check=True, env=environment)
        subprocess.run([str(python), '-I', '-X', 'faulthandler', '-u', str(Path(__file__).resolve()), '--installed', '--extra', extra, '--corpus', str(ROOT / 'corpus')], cwd=root, check=True, env=environment)
        # Native dependencies can crash after all assertions pass. Only the
        # parent can confirm that interpreter shutdown also succeeded.
        print(f'Wheel smoke passed, including interpreter shutdown ({interpreter}, cq-acis[{extra}])', flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path)
    parser.add_argument('--python', action='append', default=[])
    parser.add_argument('--extra', action='append', choices=EXTRAS, default=None,
                        help='Extras to install and smoke (default: every extra)')
    parser.add_argument('--sdist', action='store_true', help='Rebuild the sdist before installing its wheel')
    parser.add_argument('--installed', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--corpus', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.installed:
        installed_smoke(args.corpus, (args.extra or ['cadquery'])[0])
        return
    if args.dist is None:
        parser.error('--dist is required')
    interpreters = args.python or [sys.executable]
    extras = args.extra or list(EXTRAS)
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
                for extra in extras:
                    clean_install(wheels[0], interpreter, extra)
    else:
        wheels = list(args.dist.resolve().glob('*.whl'))
        if len(wheels) != 1:
            parser.error('Expected exactly one platform wheel')
        for interpreter in interpreters:
            for extra in extras:
                clean_install(wheels[0], interpreter, extra)


if __name__ == '__main__':
    main()
