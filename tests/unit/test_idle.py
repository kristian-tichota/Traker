from src.desktop import idle


def test_an_unanswered_idle_query_is_asked_again_after_the_retry_delay(monkeypatch):
    answers = [(False, None), (True, 1500)]
    asked = []
    now = [100.0]
    monkeypatch.setattr(idle, "_quiet_until", 0.0)
    monkeypatch.setattr(idle.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(idle, "session_call", lambda *call: asked.append(call) or answers.pop(0))
    assert idle.idle_ms() is None
    now[0] += idle.RETRY_S / 2
    assert idle.idle_ms() is None and len(asked) == 1
    now[0] += idle.RETRY_S
    assert idle.idle_ms() == 1500
