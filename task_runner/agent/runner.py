"""
Anthropic-compatible Agent Runner.

A lightweight runner that uses the anthropic SDK directly to execute agents defined
with the openai-agents-python Agent/Tool abstractions.

Supports:
- Multi-turn tool use loops
- Streaming output for REPL
- Structured output (via JSON mode)
- Handoff routing (simplified)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam, TextBlock, ToolResultBlockParam, ToolUseBlock

from .config import AgentAppConfig


@dataclass
class ToolDef:
    """Internal representation of a tool for Anthropic API."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class RunResult:
    """Result of a single agent run."""

    output: str
    tool_calls: list[dict] = field(default_factory=list)
    turns: int = 0
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class StreamEvent:
    """A streaming event from the runner."""

    type: str  # "text", "tool_start", "tool_result", "done", "error"
    data: str = ""
    tool_name: str | None = None
    tool_input: dict | None = None


class AnthropicRunner:
    """Runner for executing agents via Anthropic-compatible APIs."""

    def __init__(self, config: AgentAppConfig | None = None):
        self.config = config or AgentAppConfig.from_env()
        self._clients: dict[str, AsyncAnthropic] = {}

    def _get_client(self, provider: str) -> AsyncAnthropic:
        """Get or create an Anthropic client for the given provider."""
        if provider not in self._clients:
            llm_cfg = self.config.get_config(provider)
            self._clients[provider] = AsyncAnthropic(
                api_key=llm_cfg.api_key,
                base_url=llm_cfg.base_url,
            )
        return self._clients[provider]

    @staticmethod
    def _extract_tools(agent) -> list[ToolDef]:
        """Extract tools from an Agent instance into Anthropic format."""
        tools: list[ToolDef] = []
        if not hasattr(agent, "tools") or not agent.tools:
            return tools

        for tool in agent.tools:
            # Handle FunctionTool from openai-agents-python
            if hasattr(tool, "name") and hasattr(tool, "description"):
                schema = getattr(tool, "params_json_schema", {})
                tools.append(
                    ToolDef(
                        name=tool.name,
                        description=tool.description,
                        input_schema=schema if schema else {"type": "object", "properties": {}},
                    )
                )
        return tools

    @staticmethod
    def _build_anthropic_tools(tools: list[ToolDef]) -> list[dict[str, Any]]:
        """Convert ToolDef list to Anthropic tool format."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]

    @staticmethod
    def _build_system_prompt(agent) -> str | None:
        """Build system prompt from agent instructions."""
        instructions = getattr(agent, "instructions", None)
        if instructions is None:
            return None
        if callable(instructions):
            # Dynamic instructions not supported in this simplified runner
            return None
        return str(instructions)

    async def _invoke_tool(
        self, tool: Any, tool_use_id: str, tool_input: dict
    ) -> str:
        """Invoke a single tool and return its string result."""
        try:
            from agents.tool import ToolContext

            class _DummyCtx:
                pass

            args_json = json.dumps(tool_input, ensure_ascii=False)

            if hasattr(tool, "on_invoke_tool"):
                ctx = ToolContext(
                    context=_DummyCtx(),
                    tool_name=getattr(tool, "name", "unknown"),
                    tool_call_id=tool_use_id,
                    tool_arguments=args_json,
                )
                result = await tool.on_invoke_tool(ctx, args_json)
            else:
                result = "[Error] Tool has no invoke handler"

            # Normalize result to string
            if hasattr(result, "text"):
                return str(result.text)
            return str(result)
        except Exception as e:
            return f"[Error invoking tool {getattr(tool, 'name', '?')}: {type(e).__name__}: {e}]"

    async def run(
        self,
        agent,
        input_text: str,
        provider: str | None = None,
        max_turns: int = 10,
        messages: list[MessageParam] | None = None,
    ) -> RunResult:
        """Run an agent with the given input (non-streaming).

        Args:
            agent: An openai-agents-python Agent instance.
            input_text: The user input text.
            provider: LLM provider to use ("minimax" or "kimi").
            max_turns: Maximum tool-use turns.
            messages: Optional existing message history.

        Returns:
            RunResult with output and metadata.
        """
        provider = provider or self.config.default_provider
        client = self._get_client(provider)
        llm_cfg = self.config.get_config(provider)

        system_prompt = self._build_system_prompt(agent)
        tools = self._extract_tools(agent)
        anthropic_tools = self._build_anthropic_tools(tools) if tools else []

        # Initialize message history
        msgs: list[MessageParam] = list(messages) if messages else []
        msgs.append({"role": "user", "content": input_text})

        full_output = ""
        all_tool_calls: list[dict] = []
        total_usage = {"input_tokens": 0, "output_tokens": 0}

        for _turn in range(max_turns):
            response = await client.messages.create(
                model=llm_cfg.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                system=system_prompt,
                messages=msgs,
                tools=anthropic_tools if anthropic_tools else None,
            )

            total_usage["input_tokens"] += response.usage.input_tokens
            total_usage["output_tokens"] += response.usage.output_tokens

            # Process response content blocks
            tool_use_blocks: list[ToolUseBlock] = []
            text_parts: list[str] = []

            for block in response.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    tool_use_blocks.append(block)

            assistant_content: list[Any] = []
            if text_parts:
                text = "\n".join(text_parts)
                full_output += text
                assistant_content.append({"type": "text", "text": text})

            if tool_use_blocks:
                # Record tool calls
                for tub in tool_use_blocks:
                    all_tool_calls.append(
                        {
                            "id": tub.id,
                            "name": tub.name,
                            "input": tub.input,
                        }
                    )
                    assistant_content.append(
                        {
                            "type": "tool_use",
                            "id": tub.id,
                            "name": tub.name,
                            "input": tub.input,
                        }
                    )

                # Add assistant message with tool_use blocks
                msgs.append({"role": "assistant", "content": assistant_content})

                # Invoke tools and gather results
                tool_results: list[ToolResultBlockParam] = []
                for tub in tool_use_blocks:
                    tool = next(
                        (t for t in agent.tools if getattr(t, "name", None) == tub.name),
                        None,
                    )
                    if tool:
                        result_text = await self._invoke_tool(tool, tub.id, tub.input)
                    else:
                        result_text = f"[Error] Unknown tool: {tub.name}"

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tub.id,
                            "content": result_text,
                        }
                    )

                # Add tool results as user message
                msgs.append({"role": "user", "content": tool_results})
            else:
                # No tool calls — we're done
                msgs.append({"role": "assistant", "content": assistant_content})
                break

        return RunResult(
            output=full_output,
            tool_calls=all_tool_calls,
            turns=_turn + 1,
            usage=total_usage,
        )

    async def run_stream(
        self,
        agent,
        input_text: str,
        provider: str | None = None,
        max_turns: int = 10,
        messages: list[MessageParam] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Run an agent with streaming output.

        Yields StreamEvent objects for real-time display.
        """
        provider = provider or self.config.default_provider
        client = self._get_client(provider)
        llm_cfg = self.config.get_config(provider)

        system_prompt = self._build_system_prompt(agent)
        tools = self._extract_tools(agent)
        anthropic_tools = self._build_anthropic_tools(tools) if tools else []

        msgs: list[MessageParam] = list(messages) if messages else []
        msgs.append({"role": "user", "content": input_text})

        for _turn in range(max_turns):
            text_buffer = ""
            current_tool_use: dict[str, Any] | None = None
            tool_use_blocks: list[dict[str, Any]] = []

            stream = await client.messages.create(
                model=llm_cfg.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                system=system_prompt,
                messages=msgs,
                tools=anthropic_tools if anthropic_tools else None,
                stream=True,
            )

            async for event in stream:
                if event.type == "content_block_start":
                    if event.content_block.type == "tool_use":
                        current_tool_use = {
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                            "input": "",
                        }
                        yield StreamEvent(
                            type="tool_start",
                            tool_name=event.content_block.name,
                        )

                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        text_buffer += event.delta.text
                        yield StreamEvent(type="text", data=event.delta.text)
                    elif event.delta.type == "input_json_delta":
                        if current_tool_use:
                            current_tool_use["input"] += event.delta.partial_json

                elif event.type == "content_block_stop" and current_tool_use:
                    try:
                        current_tool_use["input"] = json.loads(
                            current_tool_use["input"]
                        )
                    except json.JSONDecodeError:
                        current_tool_use["input"] = {}
                    tool_use_blocks.append(current_tool_use)
                    yield StreamEvent(
                        type="tool_result",
                        tool_name=current_tool_use["name"],
                        tool_input=current_tool_use["input"],
                    )
                    current_tool_use = None

            # After stream completes, check if we need to invoke tools
            if tool_use_blocks:
                # Build assistant message
                assistant_content: list[Any] = []
                if text_buffer:
                    assistant_content.append({"type": "text", "text": text_buffer})
                for tub in tool_use_blocks:
                    assistant_content.append(
                        {
                            "type": "tool_use",
                            "id": tub["id"],
                            "name": tub["name"],
                            "input": tub["input"],
                        }
                    )
                msgs.append({"role": "assistant", "content": assistant_content})

                # Invoke tools
                tool_results: list[ToolResultBlockParam] = []
                for tub in tool_use_blocks:
                    tool = next(
                        (t for t in agent.tools if getattr(t, "name", None) == tub["name"]),
                        None,
                    )
                    if tool:
                        result_text = await self._invoke_tool(tool, tub["id"], tub["input"])
                    else:
                        result_text = f"[Error] Unknown tool: {tub['name']}"

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tub["id"],
                            "content": result_text,
                        }
                    )

                msgs.append({"role": "user", "content": tool_results})
            else:
                # No tool calls — done
                if text_buffer:
                    msgs.append(
                        {"role": "assistant", "content": [{"type": "text", "text": text_buffer}]}
                    )
                break

        yield StreamEvent(type="done", data="")
