# jira-mcp

MCP server for Jira (Server / Data Center). Provides full read/write access to issues and attachments via the Jira REST API v2.

> ⚠️ **Jira Server / Data Center only.** Not compatible with Jira Cloud — Cloud uses a different API version and authentication scheme.

## Tools

| Tool | Description |
|---|---|
| `create_issue` | Create a new issue |
| `update_issue` | Update fields of an existing issue |
| `attach_file` | Attach a local file to an issue |
| `get_issue` | Read issue details + list of attachments with IDs |
| `search_issues` | Search by JQL |
| `get_attachment_content` | Download attachment content (text files returned as string; binary files return metadata only) |

## Setup

### 1. Install dependencies

Requires **Python 3.9+**.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Generate a Personal Access Token (PAT)

In Jira Server: **your avatar → Profile → Personal Access Tokens → Create token**.

Copy the token — it's shown only once.

### 3. Configure environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `JIRA_BASE_URL` | ✅ | — | Your Jira instance URL, e.g. `https://jira.example.com` |
| `JIRA_TOKEN` | ✅* | — | Personal Access Token (PAT) |
| `JIRA_KEYCHAIN_SERVICE` | — | `jira_pat` | macOS Keychain service name (alternative to `JIRA_TOKEN`) |
| `JIRA_SSL_VERIFY` | — | `true` | Set to `false` to disable SSL verification (self-signed certs) |

*On macOS you can store the token in Keychain instead of `JIRA_TOKEN`:
```bash
security add-generic-password -a $USER -s jira_pat -w <your_token>
```

### 4. Add to Claude Desktop config

```json
{
  "mcpServers": {
    "jira_mcp": {
      "command": "/path/to/jira-mcp/venv/bin/python",
      "args": ["/path/to/jira-mcp/server.py"],
      "env": {
        "JIRA_BASE_URL": "https://jira.example.com",
        "JIRA_TOKEN": "your_token_here"
      }
    }
  }
}
```

Or with macOS Keychain (token stored separately):
```json
{
  "mcpServers": {
    "jira_mcp": {
      "command": "/path/to/jira-mcp/venv/bin/python",
      "args": ["/path/to/jira-mcp/server.py"],
      "env": {
        "JIRA_BASE_URL": "https://jira.example.com"
      }
    }
  }
}
```

## Notes

- Works with **Jira Server / Data Center** (REST API v2). Not tested with Jira Cloud.
- `get_attachment_content` reads text-based files (`.json`, `.txt`, `.xml`, `.yaml`, `.csv`, `.log`, `.md`) and returns their content directly — useful for AI assistants to read mock configs or logs attached to issues.
- `JIRA_SSL_VERIFY=false` is needed for instances with self-signed or corporate certificates.
