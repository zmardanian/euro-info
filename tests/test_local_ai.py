import support  # noqa: F401  (must come first: isolates user folders)

import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from euroinfo.core import ai
from euroinfo.ui import jobs


def stream_response(content, reason="stop"):
    response = Mock(status_code=200)
    response.iter_lines.return_value = [
        json.dumps({"message": {"content": content}}),
        json.dumps({"done": True, "done_reason": reason}),
    ]
    return response


class LocalAITests(unittest.TestCase):
    def run_job(self, responses, require_sections=True, models=("qwen3:8b",)):
        session = Mock()
        session.get.return_value.json.return_value = {"models": [{"name": name} for name in models]}
        session.post.side_effect = responses
        job = jobs.LocalSummaryJob("Evidence", "Write in Romanian.", require_sections)
        finished, chunks, chosen = [], [], []
        job.signals.finished.connect(lambda result, error: finished.append((result, error)))
        job.signals.chunk.connect(chunks.append)
        job.signals.model.connect(chosen.append)
        with patch.object(jobs.requests, "Session", return_value=session):
            job.run()
        self.assertEqual(len(finished), 1)
        session.close.assert_called_once()
        self.chosen = chosen
        return finished[0], chunks, session

    def test_http_error_shows_ollama_reason(self):
        response = Mock(status_code=500)
        response.json.return_value = {"error": "llama-server process has terminated: exit status 1"}
        (result, error), chunks, _ = self.run_job([response])
        self.assertEqual(result, "")
        self.assertIn("Ollama HTTP 500", error)
        self.assertIn("llama-server process has terminated", error)
        self.assertEqual(chunks, [])
        response.close.assert_called_once()

    def test_stream_error_is_not_silently_ignored(self):
        response = Mock(status_code=200)
        response.iter_lines.return_value = [json.dumps({"error": "GPU worker stopped"})]
        (result, error), _, _ = self.run_job([response])
        self.assertEqual(result, "")
        self.assertIn("GPU worker stopped", error)

    def test_interrupted_stream_is_not_reported_as_complete(self):
        response = Mock(status_code=200)
        response.iter_lines.return_value = [json.dumps({"message": {"content": "Partial text"}})]
        (result, error), chunks, _ = self.run_job([response])
        self.assertEqual(result, "")
        self.assertIn("before completing", error)
        self.assertEqual(chunks, ["Partial text"])

    def test_length_cutoff_continues_without_crashing(self):
        (result, error), chunks, session = self.run_job([
            stream_response("(1) Facts [1].\n(2) Assessment [1].\n(3) Critical judgment remains", "length"),
            stream_response("incomplete without context.\n(4) Watch the next vote [1]."),
        ])
        self.assertEqual(error, "")
        self.assertIn("(3)", result)
        self.assertIn("(4)", result)
        self.assertEqual(session.post.call_count, 2)
        self.assertEqual(len(chunks), 2)

    def test_complete_final_section_does_not_repeat_at_token_limit(self):
        answer = "(1) Facts [1].\n(2) Assessment [1].\n(3) Judgment [1].\n(4) Watch the vote [1]."
        (result, error), _, session = self.run_job([stream_response(answer, "length")])
        self.assertEqual((result, error), (answer, ""))
        self.assertEqual(session.post.call_count, 1)

    def test_qwen35_is_used_automatically_and_reported(self):
        answer = "(1) Facts [1].\n(2) Assessment [1].\n(3) Judgment [1].\n(4) Watch the vote [1]."
        (result, error), _, session = self.run_job(
            [stream_response(answer)], models=("qwen3.5-apps:latest", "qwen3.5:9b", "qwen3.5-tuned:latest"))
        self.assertEqual(error, "")
        self.assertEqual(self.chosen, ["qwen3.5:9b"])
        self.assertEqual(session.post.call_args.kwargs["json"]["model"], "qwen3.5:9b")
        self.assertFalse(session.post.call_args.kwargs["json"]["think"])

    def test_missing_model_names_the_recommended_one(self):
        (result, error), _, session = self.run_job([], models=("nomic-embed-text:latest",))
        self.assertEqual(result, "")
        self.assertIn(ai.RECOMMENDED_MODEL, error)
        session.post.assert_not_called()

    def test_frozen_app_does_not_pass_bundled_libraries_to_child_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = {
                "LD_LIBRARY_PATH": "/tmp/appimage/_internal",
                "LD_LIBRARY_PATH_ORIG": "/opt/user/lib",
                "_PYI_ARCHIVE_FILE": "/tmp/appimage/euro-info",
                "APPDIR": "/tmp/appimage",
                "OPENSSL_MODULES": "/tmp/appimage/_internal/ossl-modules",
                "QT_PLUGIN_PATH": "/tmp/appimage/qt/plugins",
                "OLLAMA_VULKAN": "1",
                "TMPDIR": directory,
            }
            with patch.dict(ai.os.environ, environment, clear=True):
                clean = ai.clean_environment()
            self.assertEqual(clean["LD_LIBRARY_PATH"], "/opt/user/lib")
            self.assertEqual(clean["OLLAMA_VULKAN"], "1")
            self.assertEqual(clean["TMPDIR"], directory)
            for key in ("_PYI_ARCHIVE_FILE", "APPDIR", "OPENSSL_MODULES", "QT_PLUGIN_PATH"):
                self.assertNotIn(key, clean)


class ModelChoiceTests(unittest.TestCase):
    def test_official_qwen35_tag_beats_custom_variants(self):
        installed = ["qwen3.5-apps:latest", "qwen3.5-tuned:latest", "qwen3.5:9b"]
        self.assertEqual(ai.choose_model(installed), "qwen3.5:9b")

    def test_general_variant_beats_app_building_variant(self):
        self.assertEqual(ai.choose_model(["qwen3.5-apps:latest", "qwen3.5-tuned:latest"]), "qwen3.5-tuned:latest")

    def test_older_supported_models_still_work(self):
        self.assertEqual(ai.choose_model(["qwen2.5-coder:7b", "qwen3:8b"]), "qwen3:8b")
        self.assertEqual(ai.choose_model(["qwen2.5-coder:7b"]), "qwen2.5-coder:7b")

    def test_any_chat_model_is_better_than_none_and_embeddings_are_skipped(self):
        self.assertEqual(ai.choose_model(["nomic-embed-text:latest", "phi4:14b"]), "phi4:14b")
        self.assertIsNone(ai.choose_model(["nomic-embed-text:latest"]))
        self.assertIsNone(ai.choose_model([]))

    def test_explicit_choice_must_be_installed(self):
        self.assertEqual(ai.choose_model(["a:1", "b:2"], "b:2"), "b:2")
        self.assertIsNone(ai.choose_model(["a:1"], "b:2"))

    def test_ollama_host_is_honoured(self):
        with patch.dict(ai.os.environ, {"OLLAMA_HOST": "0.0.0.0:11500"}):
            self.assertEqual(ai.base_url(), "http://127.0.0.1:11500")
        with patch.dict(ai.os.environ, {}, clear=True):
            self.assertEqual(ai.base_url(), "http://127.0.0.1:11434")


class ServiceStartTests(unittest.TestCase):
    def setUp(self):
        ai._started_process, ai._started_service = None, False

    def tearDown(self):
        ai._started_process, ai._started_service = None, False

    def test_users_systemd_service_is_preferred_over_a_new_process(self):
        readiness = iter([False, True])
        with patch.object(ai, "wait_until_ready", side_effect=lambda *_: next(readiness)), \
                patch.object(ai, "user_service_exists", return_value=True), \
                patch.object(ai.subprocess, "run", return_value=Mock(returncode=0, stderr="")) as run, \
                patch.object(ai.subprocess, "Popen") as popen:
            self.assertEqual(ai.start_service(), "systemd")
        self.assertEqual(run.call_args.args[0], ["systemctl", "--user", "start", "ollama.service"])
        popen.assert_not_called()
        self.assertTrue(ai.started_by_app())

    def test_running_server_is_left_alone(self):
        with patch.object(ai, "wait_until_ready", return_value=True), \
                patch.object(ai.subprocess, "run") as run, patch.object(ai.subprocess, "Popen") as popen:
            self.assertEqual(ai.start_service(), "running")
        run.assert_not_called()
        popen.assert_not_called()
        self.assertFalse(ai.started_by_app())

    def test_stop_only_touches_what_the_app_started(self):
        with patch.object(ai.subprocess, "run") as run:
            ai.stop_if_started()
            run.assert_not_called()
            ai._started_service = True
            ai.stop_if_started()
        self.assertEqual(run.call_args.args[0], ["systemctl", "--user", "stop", "ollama.service"])
        self.assertFalse(ai.started_by_app())


class LocalAICancellationTests(unittest.TestCase):
    def test_cancelled_before_start_does_not_open_a_connection(self):
        job = jobs.LocalSummaryJob("Evidence", "English")
        job.cancel()
        with patch.object(jobs.requests, "Session") as session:
            job.run()
        session.assert_not_called()

    def test_closed_reader_stops_processing_the_stream(self):
        job = jobs.LocalSummaryJob("Evidence", "English")
        response = Mock(status_code=200)

        def events():
            yield json.dumps({"message": {"content": "First fragment"}})
            job.cancel()
            yield json.dumps({"message": {"content": "Unwanted fragment"}})

        response.iter_lines.side_effect = lambda **kwargs: events()
        session = Mock()
        session.get.return_value.json.return_value = {"models": [{"name": "qwen3:8b"}]}
        session.post.return_value = response
        chunks, finished = [], []
        job.signals.chunk.connect(chunks.append)
        job.signals.finished.connect(lambda text, error: finished.append((text, error)))
        with patch.object(jobs.requests, "Session", return_value=session):
            job.run()
        self.assertEqual(chunks, ["First fragment"])
        self.assertEqual(finished, [("", "Analysis cancelled.")])
        response.close.assert_called_once()
        session.close.assert_called_once()


class LocalAIHeadingTests(unittest.TestCase):
    run_job = LocalAITests.run_job

    def test_markdown_final_heading_does_not_trigger_repeated_sections(self):
        answer = ("## 1. Facts\nA fact [1].\n## 2. Assessment\nContext.\n## 3. Judgment\nA judgment.\n"
                  "## 4. Developments to watch\n- Watch the vote [1].")
        (result, error), _, session = self.run_job([stream_response(answer, "length")])
        self.assertEqual((result, error), (answer, ""))
        self.assertEqual(session.post.call_count, 1)


class LocalAICompletenessTests(unittest.TestCase):
    run_job = LocalAITests.run_job

    def test_missing_sections_are_not_reported_as_a_complete_analysis(self):
        (result, error), _, _ = self.run_job([stream_response("## 1. Facts\nA fact [1].")])
        self.assertEqual(result, "")
        self.assertIn("four analysis sections", error)

    def test_second_output_limit_does_not_cache_a_cut_off_sentence(self):
        (result, error), _, _ = self.run_job([
            stream_response("(1) Facts.\n(2) Assessment.\n(3) Judgment.\n(4) Watch the", "length"),
            stream_response("next important", "length"),
        ])
        self.assertEqual(result, "")
        self.assertIn("output limit", error)


if __name__ == "__main__":
    unittest.main()
