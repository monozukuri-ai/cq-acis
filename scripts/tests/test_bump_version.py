from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from bump_version import bump_version
from check_python_release import project_version


class VersionUpdates(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.manifest = self.root / 'Cargo.toml'
        self.lockfile = self.root / 'Cargo.lock'
        self.manifest.write_text('''# Keep this comment and dependency requirement.
[workspace]
members = ["crates/acis-core", "crates/acis-py-bridge", "crates/cq-acis-py"]
resolver = "2"
[workspace.package]
version = "0.3.2" # Shared package version.
[workspace.dependencies]
acis-core = { path = "crates/acis-core", version = "=0.3.2" }
acis-py-bridge = { path = "crates/acis-py-bridge", version = "=0.3.2" }
unused-external = "1.2.3"
''', encoding='utf-8')
        (self.root / 'pyproject.toml').write_text(
            '[project]\nname = "cq-acis"\ndynamic = ["version"]\n', encoding='utf-8')
        (self.root / 'uv.lock').write_text(
            'version = 1\n[[package]]\nname = "cq-acis"\nsource = { editable = "." }\n', encoding='utf-8')
        for name in ('acis-core', 'acis-py-bridge', 'cq-acis-py'):
            directory = self.root / 'crates' / name
            (directory / 'src').mkdir(parents=True)
            (directory / 'src/lib.rs').write_text('', encoding='utf-8')
            dependencies = '\n[dependencies]\n'
            if name != 'acis-core':
                dependencies += 'acis-core.workspace = true\n'
            if name == 'cq-acis-py':
                dependencies += 'acis-py-bridge.workspace = true\n'
            (directory / 'Cargo.toml').write_text(
                f'[package]\nname = "{name}"\nversion.workspace = true\nedition = "2021"\n'
                + dependencies, encoding='utf-8')
        subprocess.run(['cargo', 'generate-lockfile', '--offline'], cwd=self.root,
                       check=True, capture_output=True)

    def snapshot(self):
        return {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def assert_locked(self, version):
        self.assertEqual(project_version(self.root), version)
        packages = tomllib.loads(self.lockfile.read_text(encoding='utf-8'))['package']
        self.assertEqual(len(packages), 3)
        self.assertTrue(all(package['version'] == version for package in packages))
        subprocess.run(['cargo', 'metadata', '--format-version', '1', '--locked', '--offline'],
                       cwd=self.root, check=True, capture_output=True)

    def test_cli_updates_all_workspace_versions_and_only_two_files(self):
        scripts = self.root / 'scripts'
        scripts.mkdir()
        for filename in ('bump_version.py', 'check_python_release.py'):
            shutil.copyfile(SCRIPTS / filename, scripts / filename)
        before = self.snapshot()
        result = subprocess.run(
            [sys.executable, str(scripts / 'bump_version.py'), '0.3.3', '--offline'],
            cwd=self.root.parent, check=True, capture_output=True, text=True)
        self.assertIn('0.3.3', result.stdout)
        self.assert_locked('0.3.3')
        after = self.snapshot()
        changed = {path for path in before if before[path] != after[path]}
        self.assertEqual(changed, {Path('Cargo.toml'), Path('Cargo.lock')})
        self.assertEqual(self.manifest.read_text(encoding='utf-8'),
                         before[Path('Cargo.toml')].decode('utf-8').replace('0.3.2', '0.3.3'))

    def test_sync_uses_only_the_representative_version(self):
        self.manifest.write_text(self.manifest.read_text(encoding='utf-8').replace(
            'version = "0.3.2"', 'version = "0.3.4"', 1), encoding='utf-8')
        self.assertEqual(bump_version(self.root, None, offline=True), '0.3.4')
        self.assert_locked('0.3.4')

    def test_same_version_repairs_a_stale_python_crate_lock_entry(self):
        self.lockfile.write_text(self.lockfile.read_text(encoding='utf-8').replace(
            'name = "cq-acis-py"\nversion = "0.3.2"',
            'name = "cq-acis-py"\nversion = "0.3.1"'), encoding='utf-8')
        bump_version(self.root, None, offline=True)
        self.assert_locked('0.3.2')

    def test_invalid_version_leaves_files_unchanged(self):
        before = self.snapshot()
        for version in ('v0.3.3', '0.3', '0.03.3', '0.3.3-rc.1', '0.3.3\n'):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, 'stable X.Y.Z'):
                bump_version(self.root, version, offline=True)
            self.assertEqual(self.snapshot(), before)

    def test_cargo_failure_restores_manifest_and_lockfile(self):
        before = self.snapshot()

        def fail(command, **kwargs):
            self.lockfile.write_text('incomplete lockfile', encoding='utf-8')
            raise subprocess.CalledProcessError(101, command)

        with patch('bump_version.subprocess.run', side_effect=fail):
            with self.assertRaises(subprocess.CalledProcessError):
                bump_version(self.root, '0.3.3', offline=True)
        self.assertEqual(self.snapshot(), before)

    def test_post_update_validation_failure_restores_both_files(self):
        before = self.snapshot()
        with patch('bump_version.project_version', side_effect=ValueError('invalid release')):
            with self.assertRaisesRegex(ValueError, 'invalid release'):
                bump_version(self.root, '0.3.3', offline=True)
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
