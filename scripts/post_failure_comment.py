import sys
import urllib.request
import json

def main():
    if len(sys.argv) < 4:
        print("Usage: post_failure_comment.py <repo> <sha> <token>")
        sys.exit(1)
        
    repo = sys.argv[1]
    sha = sys.argv[2]
    token = sys.argv[3]
    
    try:
        with open("pytest_output.log", "r", encoding="utf-8") as f:
            log_text = f.read()
    except FileNotFoundError:
        log_text = "pytest_output.log not found."

    # Truncate log to keep the relevant traceback lines (last 120 lines)
    lines = log_text.splitlines()
    if len(lines) > 120:
        log_text = "... [truncated] ...\n" + "\n".join(lines[-120:])

    payload = {
        "body": f"### ❌ CI Pytest Failure Traceback\n```text\n{log_text}\n```"
    }
    
    url = f"https://api.github.com/repos/{repo}/commits/{sha}/comments"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHub-Actions-CI",
            "Content-Type": "application/json"
        }
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            print("Successfully posted failure traceback as commit comment.")
    except Exception as e:
        print("Failed to post comment:", e)

if __name__ == "__main__":
    main()
