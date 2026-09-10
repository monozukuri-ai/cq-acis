from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_python_release import check_existing, check_tag, project_version


class SharedVersionChecks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'Cargo.toml').write_text('''
[workspace]
members = ["crates/acis-core", "crates/acis-py-bridge", "crates/cq-acis-py"]
[workspace.package]
version = "0.3.2"
[workspace.dependencies]
acis-core = { path = "crates/acis-core", version = "=0.3.2" }
acis-py-bridge = { path = "crates/acis-py-bridge", version = "=0.3.2" }
''', encoding='utf-8')
        (self.root / 'pyproject.toml').write_text('[project]\nname = "cq-acis"\ndynamic = ["version"]\n', encoding='utf-8')
        for name in ('acis-core', 'acis-py-bridge', 'cq-acis-py'):
            directory = self.root / 'crates' / name
            directory.mkdir(parents=True)
            (directory / 'Cargo.toml').write_text(f'[package]\nname = "{name}"\nversion.workspace = true\n', encoding='utf-8')

    def test_version_comes_from_rust_workspace(self):
        self.assertEqual(project_version(self.root), '0.3.2')

    def test_static_python_version_is_rejected(self):
        (self.root / 'pyproject.toml').write_text('[project]\nversion = "0.3.1"\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Python version must be inherited'):
            project_version(self.root)

    def test_independent_crate_version_is_rejected(self):
        (self.root / 'crates/acis-py-bridge/Cargo.toml').write_text(
            '[package]\nname = "acis-py-bridge"\nversion = "0.2.1"\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'acis-py-bridge must inherit'):
            project_version(self.root)

    def test_stale_dependency_pin_is_rejected(self):
        path = self.root / 'Cargo.toml'
        original = path.read_text(encoding='utf-8')
        for name in ('acis-core', 'acis-py-bridge'):
            with self.subTest(name=name):
                path.write_text(original.replace(f'path = "crates/{name}", version = "=0.3.2"',
                                                 f'path = "crates/{name}", version = "=0.2.1"'), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, f'{name} dependency must be pinned'):
                    project_version(self.root)


class ReleaseChecks(unittest.TestCase):
    def test_tag_must_identify_python_version(self):
        check_tag('v0.2.0', '0.2.0')
        check_tag('', '0.2.0')  # Manual build is allowed on a branch.
        with self.assertRaises(ValueError):
            check_tag('v0.1.0', '0.2.0')

    def test_identical_partial_release_is_retryable(self):
        check_existing({'linux.whl': 'abc', 'source.tar.gz': 'def'}, [
            {'filename': 'linux.whl', 'digests': {'sha256': 'abc'}}])

    def test_changed_file_or_old_pure_python_release_blocks_upload(self):
        local = {'cq_acis-0.1.0-cp310-abi3-win_amd64.whl': 'abc'}
        for name, digest in [('cq_acis-0.1.0-py3-none-any.whl', 'abc'),
                             ('cq_acis-0.1.0-cp310-abi3-win_amd64.whl', 'different')]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                check_existing(local, [{'filename': name, 'digests': {'sha256': digest}}])
