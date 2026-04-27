#!/usr/bin/env python3
"""Things 3 MCP Server - interact with Things 3 on macOS via AppleScript."""

import json
import logging
import os
import subprocess
import urllib.parse
from datetime import date, timedelta
from functools import wraps
from typing import Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

LOG_FILE = os.path.expanduser("~/.local/share/things-mcp/things-mcp.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE)],
)
logger = logging.getLogger("things-mcp")

mcp = FastMCP("Things 3")

# Load .env file from project directory (if it exists)
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Get Things 3 auth token from environment (required for checklist operations)
THINGS_AUTH_TOKEN = os.getenv("THINGS_AUTH_TOKEN", "")

VALID_LISTS = {"Inbox", "Today", "Upcoming", "Anytime", "Someday", "Logbook", "Trash"}
VALID_STATUSES = {"open", "completed", "cancelled", "canceled"}
# AppleScript uses American spelling; map both to the correct constant
STATUS_MAP = {"cancelled": "canceled", "canceled": "canceled", "open": "open", "completed": "completed"}
SEP = "|||"


def handle_tool_errors(func):
    """Decorator to handle errors consistently across all tools.

    Catches RuntimeError (AppleScript failures) and returns error JSON.
    Catches other exceptions, logs them, and returns generic error message.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except RuntimeError as e:
            return json.dumps({"error": str(e)})
        except Exception as e:
            logger.exception(f"Unexpected error in {func.__name__}")
            return json.dumps({"error": "Internal error — check server logs"})
    return wrapper


def run_applescript(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        err = result.stderr.strip()
        logger.error("AppleScript error: %s", err)
        raise RuntimeError(err)
    return result.stdout.strip()


def esc(s: str) -> str:
    """Escape a string for safe inclusion in an AppleScript string literal."""
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    s = s.replace("\n", '" & (ASCII character 10) & "')
    s = s.replace("\r", '" & (ASCII character 13) & "')
    return s


def open_things_url(scheme: str, auth_token: str = "") -> bool:
    """Open a Things 3 URL scheme command. Returns success status.

    Args:
        scheme: The URL scheme command (without things:///)
        auth_token: Optional auth token for write operations
    """
    if auth_token and "&" in scheme:
        url = f"things:///{scheme}&auth-token={auth_token}"
    elif auth_token:
        url = f"things:///{scheme}?auth-token={auth_token}"
    else:
        url = f"things:///{scheme}"

    result = subprocess.run(["open", url], capture_output=True)
    if result.returncode != 0:
        err = result.stderr.decode().strip()
        logger.error("URL Scheme error: %s", err)
        return False
    return True


def get_checklist_data(task_id: str) -> Optional[dict]:
    """Get full task with checklist items via things.py. Returns task dict or None."""
    try:
        import things
        task = things.todos(uuid=task_id)
        return task if task else None
    except Exception as e:
        logger.error("Error reading checklist: %s", e)
        return None


def resolve_date(value: str) -> str:
    """Convert natural language dates to YYYY-MM-DD. Validates YYYY-MM-DD format."""
    today = date.today()
    mapping = {
        "today": today,
        "tomorrow": today + timedelta(days=1),
        "yesterday": today - timedelta(days=1),
    }
    if value.lower() in mapping:
        return mapping[value.lower()].isoformat()
    try:
        date.fromisoformat(value)
        return value
    except ValueError:
        raise ValueError(f"Invalid date '{value}'. Use YYYY-MM-DD, 'today', or 'tomorrow'.")


def parse_task_lines(output: str) -> list[dict]:
    tasks = []
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split(SEP)
        if len(parts) < 11:
            logger.warning("Skipping incomplete task record: %s", line[:80])
            continue
        tasks.append({
            "id": parts[0],
            "name": parts[1],
            "notes": parts[2].replace("\\n", "\n") or None,
            "due_date": parts[3] or None,
            "when_date": parts[4] or None,
            "status": parts[5],
            "tags": [t for t in parts[6].split(",") if t],
            "project_name": parts[7] or None,
            "project_id": parts[8] or None,
            "area_name": parts[9] or None,
            "area_id": parts[10] or None,
        })
    return tasks


# AppleScript helpers included in every script that reads tasks
HELPERS = """
on formatDate(d)
    if d is missing value then return ""
    set y to (year of d) as text
    set m to ((month of d) as integer) as text
    set dy to (day of d) as text
    if length of m = 1 then set m to "0" & m
    if length of dy = 1 then set dy to "0" & dy
    return y & "-" & m & "-" & dy
end formatDate

on safeStr(val)
    if val is missing value then return ""
    set t to val as text
    set bsn to (ASCII character 92) & "n"
    set AppleScript's text item delimiters to (ASCII character 13)
    set ps to text items of t
    set AppleScript's text item delimiters to bsn
    set t to ps as text
    set AppleScript's text item delimiters to (ASCII character 10)
    set ps to text items of t
    set AppleScript's text item delimiters to bsn
    set t to ps as text
    set AppleScript's text item delimiters to "|||"
    set ps to text items of t
    set AppleScript's text item delimiters to " "
    set t to ps as text
    set AppleScript's text item delimiters to ""
    return t
end safeStr

on taskLine(t)
    tell application "Things3"
        set tid to id of t
        set tname to my safeStr(name of t)
        set tnotes to my safeStr(notes of t)
        set tdue to my formatDate(due date of t)
        set twhen to my formatDate(activation date of t)
        set tstat to status of t as text
        set tagStr to ""
        repeat with tg in tags of t
            if tagStr is not "" then set tagStr to tagStr & ","
            set tagStr to tagStr & (name of tg)
        end repeat
        set pName to ""
        set pId to ""
        if project of t is not missing value then
            set pName to my safeStr(name of project of t)
            set pId to id of project of t
        end if
        set aName to ""
        set aId to ""
        if area of t is not missing value then
            set aName to my safeStr(name of area of t)
            set aId to id of area of t
        end if
    end tell
    return tid & "|||" & tname & "|||" & tnotes & "|||" & tdue & "|||" & twhen & "|||" & tstat & "|||" & tagStr & "|||" & pName & "|||" & pId & "|||" & aName & "|||" & aId
end taskLine

on parseDate(dStr)
    if dStr is "" then return missing value
    set y to (text 1 thru 4 of dStr) as integer
    set m to (text 6 thru 7 of dStr) as integer
    set d to (text 9 thru 10 of dStr) as integer
    set dateObj to current date
    set day of dateObj to 1
    set year of dateObj to y
    set month of dateObj to m
    set day of dateObj to d
    set time of dateObj to 0
    return dateObj
end parseDate
"""


@handle_tool_errors
@mcp.tool()
def get_tasks(list_name: str = "Today") -> str:
    """
    Get tasks from a Things 3 list.

    Args:
        list_name: The list to fetch from. One of: Inbox, Today, Upcoming, Anytime, Someday, Logbook, Trash.
    """
    if list_name not in VALID_LISTS:
        return json.dumps({"error": f"list_name must be one of: {', '.join(sorted(VALID_LISTS))}"})
    script = HELPERS + f"""
tell application "Things3"
    set output to ""
    set taskList to to dos of list "{esc(list_name)}"
    repeat with t in taskList
    set output to output & my taskLine(t) & "\\n"
    end repeat
    return output
end tell
"""
    return json.dumps(parse_task_lines(run_applescript(script)), indent=2)
@handle_tool_errors
@mcp.tool()
def get_task(task_id: str) -> str:
    """
    Get full details of a single task by ID.

    Args:
        task_id: The Things 3 task ID.
    """
    script = HELPERS + f"""
tell application "Things3"
    set t to to do id "{esc(task_id)}"
    return my taskLine(t)
end tell
"""
    tasks = parse_task_lines(run_applescript(script))
    return json.dumps(tasks[0] if tasks else {"error": "Task not found"}, indent=2)
@handle_tool_errors
@mcp.tool()
def search_tasks(query: str) -> str:
    """
    Search for tasks across all lists by name.

    Args:
        query: Text to search for in task names (substring match).
    """
    script = HELPERS + f"""
tell application "Things3"
    set output to ""
    set taskList to to dos whose name contains "{esc(query)}"
    repeat with t in taskList
    set output to output & my taskLine(t) & "\\n"
    end repeat
    return output
end tell
"""
    return json.dumps(parse_task_lines(run_applescript(script)), indent=2)
@handle_tool_errors
@mcp.tool()
def get_projects() -> str:
    """Get all projects from Things 3."""
    script = HELPERS + """
tell application "Things3"
    set output to ""
    repeat with p in projects
    set pid to id of p
    set pname to my safeStr(name of p)
    set pnotes to my safeStr(notes of p)
    set pstat to status of p as text
    set tagStr to ""
    repeat with tg in tags of p
        if tagStr is not "" then set tagStr to tagStr & ","
        set tagStr to tagStr & (name of tg)
    end repeat
    set aName to ""
    set aId to ""
    if area of p is not missing value then
        set aName to my safeStr(name of area of p)
        set aId to id of area of p
    end if
    set output to output & pid & "|||" & pname & "|||" & pnotes & "|||" & pstat & "|||" & tagStr & "|||" & aName & "|||" & aId & "\\n"
    end repeat
    return output
end tell
"""
    projects = []
    for line in run_applescript(script).split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split(SEP)
        if len(parts) < 7:
            continue
        projects.append({
            "id": parts[0],
            "name": parts[1],
            "notes": parts[2].replace("\\n", "\n") or None,
            "status": parts[3],
            "tags": [t for t in parts[4].split(",") if t],
            "area_name": parts[5] or None,
            "area_id": parts[6] or None,
        })
    return json.dumps(projects, indent=2)
@handle_tool_errors
@mcp.tool()
def get_areas() -> str:
    """Get all areas from Things 3."""
    script = HELPERS + """
tell application "Things3"
    set output to ""
    repeat with a in areas
    set aid to id of a
    set aname to my safeStr(name of a)
    set tagStr to ""
    repeat with tg in tags of a
        if tagStr is not "" then set tagStr to tagStr & ","
        set tagStr to tagStr & (name of tg)
    end repeat
    set output to output & aid & "|||" & aname & "|||" & tagStr & "\\n"
    end repeat
    return output
end tell
"""
    areas = []
    for line in run_applescript(script).split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split(SEP)
        if len(parts) < 3:
            continue
        areas.append({
            "id": parts[0],
            "name": parts[1],
            "tags": [t for t in parts[2].split(",") if t],
        })
    return json.dumps(areas, indent=2)
@handle_tool_errors
@mcp.tool()
def get_tags() -> str:
    """Get all tags from Things 3."""
    script = """
tell application "Things3"
    set output to ""
    repeat with tg in tags
    set output to output & (name of tg) & "\\n"
    end repeat
    return output
end tell
"""
    tags = [line.strip() for line in run_applescript(script).split("\n") if line.strip()]
    return json.dumps(tags, indent=2)
@handle_tool_errors
@mcp.tool()
def create_task(
    title: str,
    notes: Optional[str] = None,
    deadline: Optional[str] = None,
    when_date: Optional[str] = None,
    tags: Optional[list[str]] = None,
    project_id: Optional[str] = None,
    area_id: Optional[str] = None,
    checklist_items: Optional[list[str]] = None,
) -> str:
    """
    Create a new task in Things 3.

    Args:
        title: Task title (required).
        notes: Task notes.
        deadline: Hard deadline as YYYY-MM-DD, "today", or "tomorrow".
        when_date: Scheduled start date as YYYY-MM-DD, "today", or "tomorrow".
        tags: List of tag names to apply.
        project_id: ID of the project to add the task to.
        area_id: ID of the area to add the task to (ignored if project_id is set).
        checklist_items: List of checklist item titles (max 100).
    """
    props = [f'name: "{esc(title)}"']
    if notes:
        props.append(f'notes: "{esc(notes)}"')

    extra = []
    if deadline:
        extra.append(f'set due date of newTask to my parseDate("{esc(resolve_date(deadline))}")')
    if when_date:
        extra.append(f'schedule newTask for my parseDate("{esc(resolve_date(when_date))}")')
    if tags:
        tag_str = ",".join(esc(t) for t in tags)
        extra.append(f'set tag names of newTask to "{tag_str}"')
    if project_id:
        extra.append(f'set project of newTask to project id "{esc(project_id)}"')
    elif area_id:
        extra.append(f'set area of newTask to area id "{esc(area_id)}"')

    extra_block = "\n    ".join(extra)
    script = HELPERS + f"""
tell application "Things3"
    set newTask to make new to do with properties {{{", ".join(props)}}}
    {extra_block}
    return id of newTask & "|||" & name of newTask
end tell
"""
    output = run_applescript(script)
    parts = output.split(SEP, 1)
    task_id = parts[0]
    task_name = parts[1] if len(parts) > 1 else title

    # Add checklist items if provided
    if checklist_items:
        if not THINGS_AUTH_TOKEN:
            logger.warning("THINGS_AUTH_TOKEN not set; checklist items won't be added")
        else:
            items_str = "%0a".join(urllib.parse.quote(item) for item in checklist_items)
            open_things_url(f"update?id={task_id}&checklist-items={items_str}", THINGS_AUTH_TOKEN)

    return json.dumps({"id": task_id, "name": task_name})
@handle_tool_errors
@mcp.tool()
def create_project(
    title: str,
    notes: Optional[str] = None,
    deadline: Optional[str] = None,
    when_date: Optional[str] = None,
    tags: Optional[list[str]] = None,
    area_id: Optional[str] = None,
) -> str:
    """
    Create a new project in Things 3.

    Args:
        title: Project title (required).
        notes: Project notes.
        deadline: Hard deadline as YYYY-MM-DD, "today", or "tomorrow".
        when_date: Scheduled start date as YYYY-MM-DD, "today", or "tomorrow".
        tags: List of tag names to apply.
        area_id: ID of the area to add the project to.
    """
    props = [f'name: "{esc(title)}"']
    if notes:
        props.append(f'notes: "{esc(notes)}"')

    extra = []
    if deadline:
        extra.append(f'set due date of newProj to my parseDate("{esc(resolve_date(deadline))}")')
    if when_date:
        extra.append(f'schedule newProj for my parseDate("{esc(resolve_date(when_date))}")')
    if tags:
        tag_str = ",".join(esc(t) for t in tags)
        extra.append(f'set tag names of newProj to "{tag_str}"')
    if area_id:
        extra.append(f'set area of newProj to area id "{esc(area_id)}"')

    extra_block = "\n    ".join(extra)
    script = HELPERS + f"""
tell application "Things3"
    set newProj to make new project with properties {{{", ".join(props)}}}
    {extra_block}
    return id of newProj & "|||" & name of newProj
end tell
"""
    output = run_applescript(script)
    parts = output.split(SEP, 1)
    return json.dumps({"id": parts[0], "name": parts[1] if len(parts) > 1 else title})
@handle_tool_errors
@mcp.tool()
def update_task(
    task_id: str,
    title: Optional[str] = None,
    notes: Optional[str] = None,
    deadline: Optional[str] = None,
    when_date: Optional[str] = None,
    add_tags: Optional[list[str]] = None,
    project_id: Optional[str] = None,
    area_id: Optional[str] = None,
) -> str:
    """
    Update an existing task in Things 3.

    Args:
        task_id: The Things 3 task ID (required).
        title: New title.
        notes: New notes (replaces existing notes).
        deadline: New deadline as YYYY-MM-DD, "today", "tomorrow", or "clear" to remove.
        when_date: New scheduled date as YYYY-MM-DD, "today", "tomorrow", or "clear" to remove.
        add_tags: Tag names to add (merges with existing tags).
        project_id: ID of project to move the task to.
        area_id: ID of area to move the task to (ignored if project_id is set).
    """
    lines = []
    if title is not None:
        lines.append(f'set name of t to "{esc(title)}"')
    if notes is not None:
        lines.append(f'set notes of t to "{esc(notes)}"')
    if deadline == "clear":
        lines.append("set due date of t to missing value")
    elif deadline:
        lines.append(f'set due date of t to my parseDate("{esc(resolve_date(deadline))}")')
    if when_date == "clear":
        lines.append("schedule t for missing value")
    elif when_date:
        lines.append(f'schedule t for my parseDate("{esc(resolve_date(when_date))}")')
    if add_tags:
        tag_str = ",".join(esc(tag) for tag in add_tags)
        lines.append(f"set existingTags to tag names of t")
        lines.append(f'set tag names of t to existingTags & "," & "{tag_str}"')
    if project_id:
        lines.append(f'set project of t to project id "{esc(project_id)}"')
    elif area_id:
        lines.append(f'set area of t to area id "{esc(area_id)}"')

    if not lines:
        return json.dumps({"error": "No updates specified"})

    update_block = "\n    ".join(lines)
    script = HELPERS + f"""
tell application "Things3"
    set t to to do id "{esc(task_id)}"
    {update_block}
    return id of t & "|||" & name of t
end tell
"""
    output = run_applescript(script)
    parts = output.split(SEP, 1)
    return json.dumps({"id": parts[0], "name": parts[1] if len(parts) > 1 else "", "updated": True})
@handle_tool_errors
@mcp.tool()
def update_project(
    project_id: str,
    title: Optional[str] = None,
    notes: Optional[str] = None,
    deadline: Optional[str] = None,
    when_date: Optional[str] = None,
    add_tags: Optional[list[str]] = None,
    area_id: Optional[str] = None,
) -> str:
    """
    Update an existing project in Things 3.

    Args:
        project_id: The Things 3 project ID (required).
        title: New title.
        notes: New notes (replaces existing notes).
        deadline: New deadline as YYYY-MM-DD, "today", "tomorrow", or "clear" to remove.
        when_date: New scheduled date as YYYY-MM-DD, "today", "tomorrow", or "clear" to remove.
        add_tags: Tag names to add (merges with existing tags).
        area_id: ID of area to move the project to.
    """
    lines = []
    if title is not None:
        lines.append(f'set name of p to "{esc(title)}"')
    if notes is not None:
        lines.append(f'set notes of p to "{esc(notes)}"')
    if deadline == "clear":
        lines.append("set due date of p to missing value")
    elif deadline:
        lines.append(f'set due date of p to my parseDate("{esc(resolve_date(deadline))}")')
    if when_date == "clear":
        lines.append("schedule p for missing value")
    elif when_date:
        lines.append(f'schedule p for my parseDate("{esc(resolve_date(when_date))}")')
    if add_tags:
        tag_str = ",".join(esc(tag) for tag in add_tags)
        lines.append(f"set existingTags to tag names of p")
        lines.append(f'set tag names of p to existingTags & "," & "{tag_str}"')
    if area_id:
        lines.append(f'set area of p to area id "{esc(area_id)}"')

    if not lines:
        return json.dumps({"error": "No updates specified"})

    update_block = "\n    ".join(lines)
    script = HELPERS + f"""
tell application "Things3"
    set p to project id "{esc(project_id)}"
    {update_block}
    return id of p & "|||" & name of p
end tell
"""
    output = run_applescript(script)
    parts = output.split(SEP, 1)
    return json.dumps({"id": parts[0], "name": parts[1] if len(parts) > 1 else "", "updated": True})
@handle_tool_errors
@mcp.tool()
def set_task_status(task_id: str, status: str) -> str:
    """
    Set the status of a task. Use this to reopen, cancel, or complete a task.

    Args:
        task_id: The Things 3 task ID.
        status: One of: 'open', 'completed', 'cancelled'.
    """
    if status not in VALID_STATUSES:
        return json.dumps({"error": "status must be one of: open, completed, cancelled"})
    as_status = STATUS_MAP[status]
    script = f"""
tell application "Things3"
    set t to to do id "{esc(task_id)}"
    set status of t to {as_status}
    return name of t
end tell
"""
    name = run_applescript(script)
    return json.dumps({"status": status, "task_name": name})
@handle_tool_errors
@mcp.tool()
def complete_task(task_id: str) -> str:
    """
    Mark a task as complete in Things 3.

    Args:
        task_id: The Things 3 task ID.
    """
    script = f"""
tell application "Things3"
    set t to to do id "{esc(task_id)}"
    set status of t to completed
    return name of t
end tell
"""
    name = run_applescript(script)
    return json.dumps({"completed": True, "task_name": name})
@handle_tool_errors
@mcp.tool()
def delete_task(task_id: str) -> str:
    """
    Permanently delete a task from Things 3.

    Args:
        task_id: The Things 3 task ID.
    """
    script = f"""
tell application "Things3"
    set t to to do id "{esc(task_id)}"
    set tname to name of t
    delete t
    return tname
end tell
"""
    name = run_applescript(script)
    return json.dumps({"deleted": True, "task_name": name})
@handle_tool_errors
@mcp.tool()
def add_checklist_items(task_id: str, items: list[str]) -> str:
    """Add checklist items to a task. Items are appended to existing list.

    Args:
        task_id: The Things 3 task ID.
        items: List of checklist item titles (max 100 total per task).
    """
    if not items:
        return json.dumps({"error": "items list cannot be empty"})
    if len(items) > 100:
        return json.dumps({"error": "Maximum 100 checklist items per task"})

    if not THINGS_AUTH_TOKEN:
        return json.dumps({"error": "THINGS_AUTH_TOKEN environment variable not set"})

    items_str = "%0a".join(urllib.parse.quote(item) for item in items)
    success = open_things_url(f"update?id={task_id}&append-checklist-items={items_str}", THINGS_AUTH_TOKEN)

    if success:
        return json.dumps({"added": len(items), "task_id": task_id})
    else:
        return json.dumps({"error": "Failed to add checklist items"})
@handle_tool_errors
@mcp.tool()
def get_checklist_item_status(task_id: str, item_text: str) -> str:
    """Get the completion status of a checklist item.

    Note: Marking items complete must be done in the Things 3 app directly.
    Things 3's URL Scheme does not currently support programmatic completion
    of checklist items, despite documentation suggesting it should.

    Args:
        task_id: The Things 3 task ID.
        item_text: The exact text of the checklist item to check.
    """
    task = get_checklist_data(task_id)
    if not task:
        return json.dumps({"error": "Task not found"})

    checklist = task.get("checklist", [])
    if not checklist:
        return json.dumps({"error": "Task has no checklist items"})

    # Find the item and return its status
    for item in checklist:
        if item.get("title") == item_text:
            return json.dumps({
                "item": item_text,
                "status": item.get("status"),
                "task_id": task_id
            })

    return json.dumps({"error": f"Checklist item '{item_text}' not found"})
@handle_tool_errors
@mcp.tool()
def get_task_checklist(task_id: str) -> str:
    """Get all checklist items for a task, including their completion status.

    Args:
        task_id: The Things 3 task ID.
    """
    import things
    task = things.todos(uuid=task_id)

    if not task:
        return json.dumps({"error": "Task not found"})

    checklist = task.get("checklist", [])
    return json.dumps({
        "task_id": task_id,
        "task_name": task.get("title"),
        "checklist": checklist,
        "total_items": len(checklist),
        "completed_items": sum(1 for item in checklist if item.get("completed"))
    }, indent=2)


if __name__ == "__main__":
    mcp.run()