"""当前问题和检索上下文必须排在历史对话之后。"""

from types import SimpleNamespace

from rag import generator


def test_current_question_is_last_in_normal_and_streaming_generation(monkeypatch):
    calls = []

    def create(**kwargs):
        calls.append(kwargs["messages"])
        if kwargs.get("stream"):
            return iter([SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="answer"))])])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))],
            usage=SimpleNamespace(total_tokens=1),
        )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(generator, "_get_client", lambda: fake_client)
    history = [{"role": "user", "content": "旧问题"}, {"role": "assistant", "content": "旧答案"}]

    assert generator.generate("新问题", "最新检索依据", history) == ("answer", 1)
    assert list(generator.generate_stream("新问题", "最新检索依据", history)) == ["answer"]
    for messages in calls:
        assert messages[1:3] == history
        assert messages[-1]["role"] == "user"
        assert "新问题" in messages[-1]["content"]
        assert "最新检索依据" in messages[-1]["content"]
