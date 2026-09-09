from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_python_release import check_existing, check_tag


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
