"""Tests for AgentREPL."""


from task_runner.agent.repl import AgentREPL


class TestAgentREPL:
    def test_init_no_project(self):
        repl = AgentREPL()
        assert repl.agent_session.project_name is None
        assert repl.agent_session.workspace is None

    def test_suggest_task_set_name(self):
        repl = AgentREPL()
        repl.agent_session.user_requirement = "Create product model"
        name = repl._suggest_task_set_name()
        assert name == "create-product-model"

    def test_suggest_task_set_name_fallback(self):
        repl = AgentREPL()
        repl.agent_session.user_requirement = ""
        name = repl._suggest_task_set_name()
        assert name == "generated-tasks"

    def test_suggest_with_chinese(self):
        repl = AgentREPL()
        repl.agent_session.user_requirement = "创建产品模块和测试"
        name = repl._suggest_task_set_name()
        # Chinese chars are not matched by [a-zA-Z0-9], so fallback
        assert name == "generated-tasks"
