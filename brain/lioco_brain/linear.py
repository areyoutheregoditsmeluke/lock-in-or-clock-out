"""Open Linear issues assigned to you. Optional; needs an API key in the env."""
import json
import os
import urllib.request

QUERY = """
query {
  viewer {
    assignedIssues(first: 30, orderBy: updatedAt,
      filter: { state: { type: { nin: ["completed", "canceled"] } } }) {
      nodes { identifier title priority dueDate estimate url
              state { name type } project { name } }
    }
  }
}
"""


def issues(cfg, timeout=6):
    key = os.environ.get((cfg.get("linear") or {}).get("api_key_env") or "LINEAR_API_KEY")
    if not key:
        return []
    req = urllib.request.Request(
        "https://api.linear.app/graphql",
        data=json.dumps({"query": QUERY}).encode(),
        headers={"Content-Type": "application/json", "Authorization": key},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)
    nodes = (((data.get("data") or {}).get("viewer") or {}).get("assignedIssues") or {}).get("nodes") or []
    out = []
    for n in nodes:
        out.append({
            "text": f"{n['identifier']} {n['title']}",
            "identifier": n["identifier"],
            "title": n["title"],
            "priority": n.get("priority") or 0,  # 1 urgent .. 4 low, 0 none
            "due": n.get("dueDate"),
            "estimate": n.get("estimate"),
            "state": (n.get("state") or {}).get("name"),
            "state_type": (n.get("state") or {}).get("type"),
            "project": (n.get("project") or {}).get("name"),
            "url": n.get("url"),
            "source": "linear",
        })
    return out
