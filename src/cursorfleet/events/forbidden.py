"""Field names that must never appear in a persisted event. Stdlib only.

These are Cursor payload fields (or obvious aliases) carrying prompts,
thinking, responses, file contents, command output, environment, emails or
transcript locations. The event models reject every one of them (extra="forbid"),
and security tests assert none is a model field.
"""

from __future__ import annotations

FORBIDDEN_EVENT_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "prompt",
        "thought",
        "thinking",
        "response",
        "text",
        "message",
        "content",
        "contents",
        "file_content",
        "file_contents",
        "output",
        "stdout",
        "stderr",
        "tool_input",
        "tool_output",
        "error_message",
        "edits",
        "task",
        "summary",
        "description",
        "attachments",
        "env",
        "environment",
        "user_email",
        "email",
        "transcript_path",
        "agent_transcript_path",
        "workspace_roots",
        "cwd",
        "file_path",
        "modified_files",
    }
)
