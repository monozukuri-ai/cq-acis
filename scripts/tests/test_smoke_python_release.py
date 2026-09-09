import contextlib
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smoke_python_release import clean_install


class SmokeShutdownTests(unittest.TestCase):
    def run_smoke(self, child_code):
        run = subprocess.run

        def subprocess_step(command, **kwargs):
            if '--installed' in command:
                # Exercise a real child process, including its shutdown, while
                # leaving environment creation and network installation mocked.
                return run([sys.executable, '-I', '-c', child_code],
                           check=kwargs['check'], capture_output=True, text=True)
            return subprocess.CompletedProcess(command, 0)

        with patch('smoke_python_release.subprocess.run', side_effect=subprocess_step) as calls:
            clean_install(Path('example.whl'), sys.executable)
        return calls

    def test_success_requires_normal_interpreter_shutdown(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            calls = self.run_smoke("print('Assertions passed', flush=True)")
        self.assertIn('Wheel smoke passed, including interpreter shutdown', output.getvalue())
        install = next(call for call in calls.call_args_list if 'install' in call.args[0])
        self.assertIn('--only-binary=:all:', install.args[0])
        child = calls.call_args_list[-1]
        self.assertIn('-I', child.args[0])
        self.assertIn('faulthandler', child.args[0])
        self.assertTrue(child.kwargs['check'])

    def test_passing_assertions_do_not_hide_shutdown_failure(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(subprocess.CalledProcessError) as error:
            self.run_smoke(
                "import atexit, os; atexit.register(os._exit, 7); "
                "print('Assertions passed', flush=True)"
            )
        self.assertEqual(error.exception.returncode, 7)
        self.assertIn('Assertions passed', error.exception.stdout)
        self.assertNotIn('Wheel smoke passed', output.getvalue())
