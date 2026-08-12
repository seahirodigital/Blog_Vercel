import unittest
from contextlib import redirect_stdout
from io import StringIO

from scripts.accessories.macos_launcher import LauncherRequest, main, parse_launcher_url, terminal_command


FIRST_JOB = "123e4567-e89b-42d3-a456-426614174000"
SECOND_JOB = "123e4567-e89b-42d3-a456-426614174001"
BATCH_ID = "123e4567-e89b-42d3-a456-426614174099"


class MacOsLauncherTest(unittest.TestCase):
    def test_accepts_legacy_uuid_job_ids_without_fixed_count_limit(self):
        url = f"blogvercel-mlx://run?job_id={FIRST_JOB}&job_id={SECOND_JOB}"
        self.assertEqual((FIRST_JOB, SECOND_JOB), parse_launcher_url(url).job_ids)

    def test_accepts_one_batch_id(self):
        request = parse_launcher_url(f"blogvercel-mlx://run?batch_id={BATCH_ID}")
        self.assertEqual(BATCH_ID, request.batch_id)
        self.assertEqual((), request.job_ids)

    def test_rejects_unknown_scheme_action_and_parameters(self):
        invalid_urls = [
            f"https://run?job_id={FIRST_JOB}",
            f"blogvercel-mlx://delete?job_id={FIRST_JOB}",
            f"blogvercel-mlx://run?job_id={FIRST_JOB}&command=open",
            f"blogvercel-mlx://run?batch_id={BATCH_ID}&job_id={FIRST_JOB}",
            "blogvercel-mlx://run?job_id=not-a-uuid",
        ]
        for url in invalid_urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                parse_launcher_url(url)

    def test_terminal_command_only_contains_fixed_worker_and_job_flags(self):
        command = terminal_command(LauncherRequest(job_ids=(FIRST_JOB, SECOND_JOB)))
        self.assertTrue(command.startswith("'/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_accessories_worker.command'"))
        self.assertEqual(2, command.count("--job-id"))
        self.assertNotIn(";", command)

    def test_terminal_command_uses_batch_id_without_enumerating_jobs(self):
        command = terminal_command(LauncherRequest(batch_id=BATCH_ID))
        self.assertIn(f"--batch-id {BATCH_ID}", command)
        self.assertNotIn("--job-id", command)

    def test_print_command_mode_does_not_open_terminal(self):
        output = StringIO()
        with redirect_stdout(output):
            status = main(["--print-command", f"blogvercel-mlx://run?job_id={FIRST_JOB}"])
        self.assertEqual(0, status)
        self.assertIn(f"--job-id {FIRST_JOB}", output.getvalue())


if __name__ == "__main__":
    unittest.main()
