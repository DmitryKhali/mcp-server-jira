import os
import json
import subprocess
from typing import Optional
import httpx
from mcp.server.fastmcp import FastMCP


KEYCHAIN_SERVICE = os.getenv("JIRA_KEYCHAIN_SERVICE", "jira_pat")
JIRA_SSL_VERIFY = os.getenv("JIRA_SSL_VERIFY", "true").lower() != "false"


def _get_base_url() -> str:
    url = os.getenv("JIRA_BASE_URL", "").rstrip("/")
    if not url:
        raise RuntimeError(
            "JIRA_BASE_URL environment variable is required.\n"
            "Example: export JIRA_BASE_URL=https://your-jira.example.com"
        )
    return url


def get_token() -> str:
    """Get Jira PAT from JIRA_TOKEN env var or macOS Keychain."""
    token = os.getenv("JIRA_TOKEN", "").strip()
    if token:
        return token
    result = subprocess.run(
        ["security", "find-generic-password", "-a", os.getenv("USER", ""), "-s", KEYCHAIN_SERVICE, "-w"],
        capture_output=True,
        text=True,
    )
    token = result.stdout.strip()
    if not token:
        raise RuntimeError(
            f"Jira token not found.\n"
            f"Option 1 — env var:      export JIRA_TOKEN=<your_token>\n"
            f"Option 2 — macOS Keychain: security add-generic-password -a $USER -s {KEYCHAIN_SERVICE} -w <your_token>"
        )
    return token


def _jira_client() -> httpx.Client:
    return httpx.Client(
        headers={
            "Authorization": f"Bearer {get_token()}",
            "Content-Type": "application/json",
        },
        verify=JIRA_SSL_VERIFY,
        timeout=30.0,
    )


mcp = FastMCP("jira_mcp")


@mcp.tool()
def create_issue(
    project: str,
    summary: str,
    description: str = "",
    issue_type: str = "Bug",
    labels: Optional[list[str]] = None,
    parent: Optional[str] = None,
    assignee: Optional[str] = None,
    priority: str = "Medium",
    component_ids: Optional[list[str]] = None,
    environment: Optional[str] = None,
) -> str:
    """Create a new issue in Jira.

    Args:
        project: Project key, e.g. MYPROJECT
        summary: Issue title — plain text
        description: Body in Jira wiki markup
        issue_type: Issue type name, e.g. Bug, Task, Story
        labels: Label strings, e.g. ["backend"] or ["mobile"]
        parent: Parent issue key, e.g. "MYPROJECT-123"
        assignee: Jira username, e.g. "john.doe"
        priority: Priority name, e.g. Medium, High, Critical
        component_ids: Component IDs as strings, e.g. ["10100"]
        environment: Device/OS string for the Environment field

    Returns:
        JSON with created issue key and URL
    """
    base_url = _get_base_url()
    fields: dict = {
        "project": {"key": project},
        "summary": summary,
        "issuetype": {"name": issue_type},
        "priority": {"name": priority},
    }

    if description:
        fields["description"] = description
    if labels:
        fields["labels"] = labels
    if parent:
        fields["parent"] = {"key": parent}
    if assignee:
        fields["assignee"] = {"name": assignee}
    if component_ids:
        fields["components"] = [{"id": cid} for cid in component_ids]
    if environment:
        fields["environment"] = environment

    with _jira_client() as client:
        resp = client.post(
            f"{base_url}/rest/api/2/issue",
            json={"fields": fields},
        )
        resp.raise_for_status()
        data = resp.json()

    issue_key = data.get("key", "")
    return json.dumps(
        {
            "key": issue_key,
            "url": f"{base_url}/browse/{issue_key}",
            "id": data.get("id"),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def update_issue(
    issue_key: str,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    assignee: Optional[str] = None,
    priority: Optional[str] = None,
    labels: Optional[list[str]] = None,
    environment: Optional[str] = None,
) -> str:
    """Update fields of an existing Jira issue.

    Args:
        issue_key: Jira issue key, e.g. MYPROJECT-456
        summary: New title (plain text)
        description: New body in Jira wiki markup
        assignee: Jira username
        priority: Priority name, e.g. Medium, High
        labels: Label strings, e.g. ["backend"]
        environment: Device/OS string for the Environment field

    Returns:
        JSON with issue key and URL
    """
    base_url = _get_base_url()
    fields: dict = {}

    if summary is not None:
        fields["summary"] = summary
    if description is not None:
        fields["description"] = description
    if assignee is not None:
        fields["assignee"] = {"name": assignee}
    if priority is not None:
        fields["priority"] = {"name": priority}
    if labels is not None:
        fields["labels"] = labels
    if environment is not None:
        fields["environment"] = environment

    if not fields:
        raise ValueError("No fields to update — provide at least one parameter")

    with _jira_client() as client:
        resp = client.put(
            f"{base_url}/rest/api/2/issue/{issue_key}",
            json={"fields": fields},
        )
        resp.raise_for_status()

    return json.dumps(
        {
            "key": issue_key,
            "url": f"{base_url}/browse/{issue_key}",
            "updated_fields": list(fields.keys()),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def attach_file(issue_key: str, file_path: str) -> str:
    """Attach a file to an existing Jira issue.

    Args:
        issue_key: Jira issue key, e.g. MYPROJECT-456
        file_path: Absolute path to the file on disk

    Returns:
        JSON with attachment id, filename and issue URL
    """
    base_url = _get_base_url()
    path = os.path.expanduser(file_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {path}")

    filename = os.path.basename(path)
    with open(path, "rb") as f:
        file_bytes = f.read()

    with httpx.Client(
        headers={
            "Authorization": f"Bearer {get_token()}",
            "X-Atlassian-Token": "no-check",
        },
        verify=JIRA_SSL_VERIFY,
        timeout=60.0,
    ) as client:
        resp = client.post(
            f"{base_url}/rest/api/2/issue/{issue_key}/attachments",
            files={"file": (filename, file_bytes)},
        )
        resp.raise_for_status()
        data = resp.json()

    attachment = data[0] if isinstance(data, list) else data
    return json.dumps(
        {
            "id": attachment.get("id"),
            "filename": attachment.get("filename"),
            "issue_key": issue_key,
            "url": f"{base_url}/browse/{issue_key}",
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def get_issue(issue_key: str) -> str:
    """Get full details of a Jira issue, including attachment list.

    Args:
        issue_key: Jira issue key, e.g. MYPROJECT-456

    Returns:
        JSON with key, summary, description, status, assignee, priority,
        labels, components, environment, and attachments list with IDs
    """
    base_url = _get_base_url()
    with _jira_client() as client:
        resp = client.get(
            f"{base_url}/rest/api/2/issue/{issue_key}",
            params={"fields": "summary,description,status,assignee,priority,labels,components,environment,attachment"},
        )
        resp.raise_for_status()
        data = resp.json()

    fields = data.get("fields", {})
    attachments = [
        {
            "id": a.get("id"),
            "filename": a.get("filename"),
            "mimeType": a.get("mimeType"),
            "size": a.get("size"),
        }
        for a in fields.get("attachment", [])
    ]

    return json.dumps(
        {
            "key": data.get("key"),
            "url": f"{base_url}/browse/{data.get('key')}",
            "summary": fields.get("summary"),
            "description": fields.get("description"),
            "status": fields.get("status", {}).get("name"),
            "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
            "priority": fields.get("priority", {}).get("name") if fields.get("priority") else None,
            "labels": fields.get("labels", []),
            "components": [c.get("name") for c in fields.get("components", [])],
            "environment": fields.get("environment"),
            "attachments": attachments,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def search_issues(jql: str, max_results: int = 20) -> str:
    """Search Jira issues using JQL.

    Args:
        jql: JQL query string, e.g. 'project = MYPROJECT AND status = Open'
        max_results: Maximum number of results, default 20

    Returns:
        JSON with total count and list of issues (key, summary, status, assignee, priority, labels)
    """
    base_url = _get_base_url()
    with _jira_client() as client:
        resp = client.get(
            f"{base_url}/rest/api/2/search",
            params={
                "jql": jql,
                "maxResults": max_results,
                "fields": "summary,status,assignee,priority,labels",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    issues = []
    for issue in data.get("issues", []):
        f = issue.get("fields", {})
        issues.append(
            {
                "key": issue.get("key"),
                "url": f"{base_url}/browse/{issue.get('key')}",
                "summary": f.get("summary"),
                "status": f.get("status", {}).get("name"),
                "assignee": f.get("assignee", {}).get("displayName") if f.get("assignee") else None,
                "priority": f.get("priority", {}).get("name") if f.get("priority") else None,
                "labels": f.get("labels", []),
            }
        )

    return json.dumps(
        {"total": data.get("total"), "returned": len(issues), "issues": issues},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def get_attachment_content(attachment_id: str) -> str:
    """Download and return the content of a Jira attachment.

    Use get_issue first to get attachment IDs.
    Text-based files (JSON, txt, xml, yaml, csv, log, md) are returned as content string.
    Binary files (images, video) return metadata only.

    Args:
        attachment_id: Attachment ID from get_issue response

    Returns:
        JSON with filename, mimeType, and content string (for text files)
        or metadata-only with a note (for binary files)
    """
    TEXT_MIME_PREFIXES = ("text/", "application/json", "application/xml", "application/javascript")
    TEXT_EXTENSIONS = (".json", ".txt", ".xml", ".csv", ".log", ".yaml", ".yml", ".md")

    base_url = _get_base_url()
    with _jira_client() as client:
        meta_resp = client.get(f"{base_url}/rest/api/2/attachment/{attachment_id}")
        meta_resp.raise_for_status()
        meta = meta_resp.json()

        mime_type = meta.get("mimeType", "")
        filename = meta.get("filename", "")
        size = meta.get("size", 0)
        content_url = meta.get("content", "")

        is_text = any(mime_type.startswith(p) for p in TEXT_MIME_PREFIXES) or any(
            filename.lower().endswith(ext) for ext in TEXT_EXTENSIONS
        )

        if not is_text:
            return json.dumps(
                {
                    "id": attachment_id,
                    "filename": filename,
                    "mimeType": mime_type,
                    "size": size,
                    "note": "Binary file — content not returned.",
                    "content_url": content_url,
                },
                ensure_ascii=False,
                indent=2,
            )

        content_resp = client.get(content_url)
        content_resp.raise_for_status()

    return json.dumps(
        {
            "id": attachment_id,
            "filename": filename,
            "mimeType": mime_type,
            "size": size,
            "content": content_resp.text,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def transition_issue(issue_key: str, status_name: str) -> str:
    """Change the status of a Jira issue by transition name.

    Fetches available transitions for the issue and applies the one
    matching status_name (case-insensitive). If no match is found,
    returns the list of available transitions.

    Args:
        issue_key: Jira issue key, e.g. MYPROJECT-456
        status_name: Target status name, e.g. "In Progress", "Done", "Closed"

    Returns:
        JSON with result: new status on success, or available transitions on mismatch
    """
    base_url = _get_base_url()

    with _jira_client() as client:
        # Get available transitions
        resp = client.get(f"{base_url}/rest/api/2/issue/{issue_key}/transitions")
        resp.raise_for_status()
        transitions = resp.json().get("transitions", [])

        # Find matching transition (case-insensitive)
        match = next(
            (t for t in transitions if t["to"]["name"].lower() == status_name.lower()),
            None,
        )

        if not match:
            available = [t["to"]["name"] for t in transitions]
            return json.dumps(
                {
                    "error": f"Transition to '{status_name}' not found",
                    "available_statuses": available,
                },
                ensure_ascii=False,
                indent=2,
            )

        # Apply transition
        resp = client.post(
            f"{base_url}/rest/api/2/issue/{issue_key}/transitions",
            json={"transition": {"id": match["id"]}},
        )
        resp.raise_for_status()

    return json.dumps(
        {
            "key": issue_key,
            "url": f"{base_url}/browse/{issue_key}",
            "status": match["to"]["name"],
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def delete_attachment(attachment_id: str) -> str:
    """Delete an attachment from a Jira issue by attachment ID.

    Use get_issue first to find attachment IDs.

    Args:
        attachment_id: Attachment ID, e.g. "1754310"

    Returns:
        JSON with confirmation of deletion
    """
    base_url = _get_base_url()

    with _jira_client() as client:
        resp = client.delete(f"{base_url}/rest/api/2/attachment/{attachment_id}")
        resp.raise_for_status()

    return json.dumps(
        {"deleted": True, "attachment_id": attachment_id},
        ensure_ascii=False,
        indent=2,
    )


if __name__ == "__main__":
    mcp.run()
