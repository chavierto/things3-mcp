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

**4. Set up auth token for checklist operations**

Copy `.env.example` to `.env` and add your Things 3 auth token:

```bash
cp .env.example .env
```

Then edit `.env` and add your token (get it from Things 3 settings → Advanced → URL Scheme & Automations):

```
THINGS_AUTH_TOKEN=your_token_here
```

The `.env` file is git-ignored, so your token won't be committed.

**5. Add to Claude Desktop config**

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

**6. Restart Claude Desktop**

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
| `update_project` | Update any field on an existing project |
| `set_task_status` | Set a task to `open`, `completed`, or `cancelled` |
| `complete_task` | Mark a task as complete |
| `delete_task` | Permanently delete a task |
| `create_task` (with checklist) | Create task with initial checklist items |
| `add_checklist_items` | Append items to a task's checklist |
| `get_task_checklist` | Read all checklist items and their completion status |
| `get_checklist_item_status` | Check the status of a single checklist item |

### Date and tag handling

**Dates** accept `YYYY-MM-DD`, `"today"`, or `"tomorrow"`. Pass `"clear"` to remove a date.

**Tags** can contain any characters, including slashes and spaces (e.g., `"Important/Due soon"`). When adding multiple tags via `add_tags`, each tag is created separately:
- `add_tags=["Tag1", "Tag2"]` creates two distinct tags, not one concatenated tag
- Existing tags are preserved; new tags are merged in

### Checklist functionality

**Creating and managing checklists:**
- `create_task(..., checklist_items=["Item 1", "Item 2"])` — create task with initial checklist
- `add_checklist_items(task_id, ["Item 3", "Item 4"])` — append items to existing checklist
- `get_task_checklist(task_id)` — read all items and see which are complete
- `get_checklist_item_status(task_id, "Item 1")` — check status of single item

**Important:** Completing checklist items must be done in the Things 3 app. The Things URL Scheme does not currently support programmatic completion of checklist items, despite the documentation. You can create and read checklists via the MCP, but marking items complete must be done manually in the app.

**Requirements:** Checklist write operations require `THINGS_AUTH_TOKEN` to be set in your `.env` file (see Installation step 4). Your token is stored locally in the project and is git-ignored.

## Example usage

> "What's on my Today list?"

> "Add a task to call the dentist next Tuesday"

> "Move the household budget tasks to the Finance area"

> "Mark everything tagged 'waiting' as complete"

## How it works

Claude talks to the MCP server over stdio. The server translates tool calls into AppleScript commands sent to Things 3 via `osascript`. No network requests, no API keys, no Things URL scheme required.

Since Things 3 syncs via Things Cloud, anything created or modified on Mac will automatically appear on iPhone and iPad.

## Logs

The server writes warnings and errors to:

```
~/.local/share/things-mcp/things-mcp.log
```

To watch logs in real time:

```bash
tail -f ~/.local/share/things-mcp/things-mcp.log
```

## License

MIT
