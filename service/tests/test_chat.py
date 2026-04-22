"""Chat prompt construction tests."""

from npu_service.core.chat import SYSTEM_PROMPT, ChatMessage, build_prompt


def test_build_prompt_includes_system_and_history() -> None:
    history = [
        ChatMessage(
            "assistant",
            "You are chatting with the local TinyLlama model running on the Intel NPU. "
            "Type a message in English and press Enter.",
        ),
        ChatMessage("user", "hello"),
        ChatMessage("assistant", "Hi there!"),
        ChatMessage("user", "what can you do?"),
        ChatMessage("assistant", "I can answer questions and help with local NPU validation."),
    ]

    prompt = build_prompt(history, "great, summarize that")

    assert SYSTEM_PROMPT in prompt
    assert "User: hello" in prompt
    assert "Assistant: Hi there!" in prompt
    assert "User: what can you do?" in prompt
    assert "Assistant: I can answer questions and help with local NPU validation." in prompt
    assert prompt.endswith("Assistant:")
