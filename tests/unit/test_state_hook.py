import logging
import threading

from src.desktop.hooks import StateHook


class BlockingRun:
    def __init__(self):
        self.commands = []
        self.started = threading.Event()
        self.release = threading.Event()

    def __call__(self, command, **kwargs):
        self.commands.append(command)
        self.started.set()
        self.release.wait(5)
        return type("Finished", (), {"returncode": 0, "stderr": ""})()


class TestTheCommand:
    def test_it_hears_the_state_in_place_of_the_placeholder(self, tmp_path):
        heard = tmp_path / "heard"
        hook = StateHook(f"printf '%s\\n' {{state}} >> {heard}")

        hook.tell("document")
        hook.close()

        assert heard.read_text() == "document\n"

    def test_a_state_told_twice_runs_once(self, tmp_path):
        heard = tmp_path / "heard"
        hook = StateHook(f"printf '%s\\n' {{state}} >> {heard}")

        hook.tell("break")
        hook.tell("break")
        hook.close()

        assert heard.read_text() == "break\n"

    def test_a_burst_told_while_it_runs_is_one_run_of_the_latest(self):
        run = BlockingRun()
        hook = StateHook("follow {state}", run=run)

        hook.tell("break")
        run.started.wait(5)
        hook.tell("document")
        hook.tell("video")
        run.release.set()
        hook.close()

        assert run.commands == ["follow break", "follow video"]

    def test_a_burst_that_comes_back_runs_nothing_more(self):
        run = BlockingRun()
        hook = StateHook("follow {state}", run=run)

        hook.tell("break")
        run.started.wait(5)
        hook.tell("document")
        hook.tell("break")
        run.release.set()
        hook.close()

        assert run.commands == ["follow break"]


class TestWhatGoesWrong:
    def test_a_failing_command_is_one_warning_however_often_it_fails(self, caplog):
        hook = StateHook("echo refused >&2; exit 3")

        with caplog.at_level(logging.DEBUG, logger="src.desktop.hooks"):
            hook.tell("break")
            hook.tell("focus")
            hook.close()

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert [r.getMessage() for r in warnings] == ["The state hook failed for 'break': refused"]

    def test_without_a_command_nothing_runs_and_the_state_is_still_kept(self):
        hook = StateHook("")

        hook.tell("deck")

        assert hook.told == "deck"
        hook.close()

    def test_a_closed_hook_takes_no_more(self):
        run = BlockingRun()
        run.release.set()
        hook = StateHook("follow {state}", run=run)
        hook.close()

        hook.tell("break")

        assert run.commands == []
