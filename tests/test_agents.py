from finbench.agents.backends import AssistantTurn, ScriptedBackend, ToolCall
from finbench.agents.loop import BASH_TOOL


def test_scripted_backend_returns_queued_then_done():
    t1 = AssistantTurn(text="", tool_calls=[ToolCall(id="1", name="bash", arguments={"command": "ls"})])
    b = ScriptedBackend(turns=[t1])
    assert b.chat([], BASH_TOOL) is t1          # first queued turn
    assert b.chat([], BASH_TOOL).text == "done"  # exhausted -> stop turn
    assert b.chat([], BASH_TOOL).tool_calls == []


def test_assistant_message_shape_with_tool_calls():
    turn = AssistantTurn(
        text="working",
        tool_calls=[ToolCall(id="abc", name="bash", arguments={"command": "pytest"})],
    )
    msg = ScriptedBackend(turns=[]).assistant_message(turn)
    assert msg["role"] == "assistant"
    assert msg["content"] == "working"
    assert msg["tool_calls"][0]["id"] == "abc"
    assert msg["tool_calls"][0]["function"]["name"] == "bash"
    # arguments is a JSON string per the OpenAI wire format
    assert '"command": "pytest"' in msg["tool_calls"][0]["function"]["arguments"]


def test_bash_tool_schema():
    fn = BASH_TOOL[0]["function"]
    assert fn["name"] == "bash"
    assert fn["parameters"]["required"] == ["command"]
