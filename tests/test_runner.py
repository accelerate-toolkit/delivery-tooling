# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Exercise runner boundaries without contacting GitHub or executing Renovate."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

RUNNER = Path(__file__).resolve().parents[1] / "actions/renovate/run.sh"


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        fake = self.root / "npx"
        fake.write_text(f"#!{sys.executable}\n" + '''import json, os, sys
keys = ['RENOVATE_REPOSITORIES', 'RENOVATE_AUTODISCOVER', 'RENOVATE_ONBOARDING',
        'RENOVATE_REQUIRE_CONFIG', 'RENOVATE_DRY_RUN', 'RENOVATE_PLATFORM',
        'RENOVATE_BINARY_SOURCE', 'GOPRIVATE']
print(json.dumps({'args': sys.argv[1:], 'env': {k: os.environ.get(k) for k in keys},
                  'token_forwarded': os.environ['GITHUB_TOKEN'] == os.environ['RENOVATE_TOKEN']}))
sys.exit(int(os.environ.get('FAKE_EXIT', '0')))
''')
        fake.chmod(0o755)
        self.env = {
            "PATH": f"{self.root}{os.pathsep}{os.environ['PATH']}",
            "RENOVATE_TOKEN": "test-only-secret-not-a-real-token",
            "BOT_VERSION": "44.151.0",
            "CALLER_REPOSITORY": "example/renamed-project",
        }

    def run_runner(self, **updates):
        return subprocess.run(["bash", str(RUNNER)], env=self.env | updates,
                              cwd=self.root, capture_output=True, text=True)

    def test_preview_is_default_and_target_is_caller(self):
        result = self.run_runner(RENOVATE_REPOSITORIES="example/old-project",
                                 RENOVATE_AUTODISCOVER="true", RENOVATE_ONBOARDING="true")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['args'], ['--yes', '--package=renovate@44.151.0', 'renovate'])
        self.assertEqual(payload['env']['RENOVATE_REPOSITORIES'], 'example/renamed-project')
        self.assertEqual(payload['env']['RENOVATE_AUTODISCOVER'], 'false')
        self.assertEqual(payload['env']['RENOVATE_ONBOARDING'], 'false')
        self.assertEqual(payload['env']['RENOVATE_REQUIRE_CONFIG'], 'required')
        self.assertEqual(payload['env']['RENOVATE_DRY_RUN'], 'full')
        self.assertTrue(payload['token_forwarded'])

    def test_explicit_normal_run_and_private_module_environment(self):
        result = self.run_runner(RENOVATE_DRY_RUN="", GOPRIVATE="github.com/example/*")
        self.assertEqual(result.returncode, 0, result.stderr)
        env = json.loads(result.stdout)['env']
        self.assertEqual(env['RENOVATE_DRY_RUN'], '')
        self.assertEqual(env['GOPRIVATE'], 'github.com/example/*')

    def test_invalid_inputs_never_invoke_npx_or_print_token(self):
        for invalid in [{"RENOVATE_TOKEN": ""}, {"BOT_VERSION": "latest"},
                        {"BOT_VERSION": "44.151.0; touch unwanted"},
                        {"APM_VERSION": "latest"}, {"RENOVATE_DRY_RUN": "extract"},
                        {"CALLER_REPOSITORY": "example/one,example/two"},
                        {"CALLER_REPOSITORY": ""}]:
            with self.subTest(invalid=invalid):
                result = self.run_runner(**invalid)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')
                self.assertNotIn(self.env['RENOVATE_TOKEN'], result.stderr)

    def test_preflight_does_not_run_renovate(self):
        result = subprocess.run(['bash', str(RUNNER), '--check'],
                                env=self.env | {'APM_VERSION': '0.33.0'},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')

    def test_renovate_failure_is_propagated(self):
        self.assertEqual(self.run_runner(FAKE_EXIT='17').returncode, 17)


if __name__ == '__main__':
    unittest.main()
