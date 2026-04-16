# things3-mcp

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that gives Claude full read/write access to [Things 3](https://culturedcode.com/things/) on macOS via AppleScript.

Ask Claude to create tasks, search your lists, reschedule things, complete items, and more — all without leaving your conversation.

## Requirements

- macOS
- [Things 3](https://culturedcode.com/things/) installed and running
- [Claude Desktop](https://claude.ai/download)
- [uv](https://docs.astral.sh/uv/) (Python package manager)

## Installation

**1. Clone the repo**

```bash
git clone https://github.com/chavierto/things3-mcp.git
cd things3-mcp
```

**2. Install uv** (if you don't have it)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**3. Install dependencies**

```bash
uv sync
```

**4. Add to Claude Desktop config**

Open `~/Library/Application Support/Claude/claude_desktop_config.json` and add:

```json
{
  "mcpServers": {
    "things3": {
      "command": "/path/to/uv",
      "args": ["--directory", "/path/to/things3-mcp", "run", "server.py"]
    }
  }
}
```

Replace `/path/to/uv` with the output of `which uv` and `/path/to/things3-mcp` with the folder you cloned into.

**5. Restart Claude Desktop**

Things 3 must be open and running when Claude Desktop starts.

## Available tools

| Tool | Description |
|------|-------------|
| `get_tasks` | Fetch tasks from a list (Today, Inbox, Upcoming, Anytime, Someday, Logbook, Trash) |
| `get_task` | Get full details of a task by ID |
| `search_tasks` | Search across all tasks by keyword |
| `get_projects` | List all projects |
| `get_areas` | List all areas |
| `get_tags` | List all tags |
| `create_task` | Create a task with title, notes, deadline, when-date, tags, project, or area |
| `create_project` | Create a project with the same options |
| `update_task` | Update any field on an existing task |
| `complete_task` | Mark a task as complete |

## Example usage

> "What's on my Today list?"

> "Add a task to call the dentist next Tuesday"

> "Move the Ritmo project tasks to the Finance area"

> "Mark everything tagged 'waiting' as complete"

## How it works

Claude talks to the MCP server over stdio. The server translates tool calls into AppleScript commands sent to Things 3 via `osascript`. No network requests, no API keys, no Things URL scheme required.

Since Things 3 syncs via Things Cloud, anything created or modified on Mac will automatically appear on iPhone and iPad.

## License

MIT
