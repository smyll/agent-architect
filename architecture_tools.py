"""Three read-only tools. Network access is limited to named official docs pages."""
import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

from strands import tool

ROOT = Path(__file__).parent
DOCS = {
    "quickstart": "https://strandsagents.com/docs/user-guide/quickstart/python/",
    "tools": "https://strandsagents.com/docs/user-guide/concepts/tools/",
    "model_provider": "https://strandsagents.com/docs/user-guide/concepts/model-providers/openai/",
}
TEMPLATES = {"basic": ROOT / "templates/basic.py.txt", "tools": ROOT / "templates/tools.py.txt"}


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def fetch_document(topic):
    url = DOCS[topic]
    request = Request(url, headers={"User-Agent": "AgentArchitect-MVP/0.1"})
    with urlopen(request, timeout=20) as response:
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Documentation page too large")
    parser = PageText()
    parser.feed(raw.decode("utf-8"))
    text = "\n".join(parser.parts)
    # Skip global navigation; page headings follow its 'On this page' navigation.
    markers = {"quickstart": "#unused", "tools": "Tools are the primary mechanism",
               "model_provider": "OpenAI is configured as an optional dependency"}
    marker = markers[topic]
    if topic == "quickstart":
        marker = "Python 3.10"
    start = text.find(marker)
    if start >= 0:
        text = text[max(0, start - 180):]
    if len(text) < 200:
        raise ValueError("Empty documentation")
    return {"topic": topic, "source": url, "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "excerpt": text[:12000], "truncated": len(text) > 12000}


class ArchitectureTools:
    def __init__(self):
        self.trace = []
        self.documents = {}
        self.patterns = {}
        self.templates = {}

        def record(name, arguments, operation):
            entry = {"tool": name, "arguments": arguments, "status": "running"}
            self.trace.append(entry)
            try:
                result = operation()
            except Exception:
                entry["status"] = "failed"
                return {"error": "Tool unavailable; do not invent its result."}
            entry.update(status="success", result=result)
            return result

        @tool
        def retrieve_strands_docs(topic: str) -> dict:
            """Read official Strands documentation online before designing the skeleton.

            Args:
                topic: One of quickstart, tools, model_provider.
            """
            def run():
                result = fetch_document(topic)
                self.documents[topic] = result
                return result
            return record("retrieve_strands_docs", {"topic": topic}, run)

        @tool
        def lookup_agent_pattern(name: str) -> dict:
            """Read a local architecture pattern. Choose by confirmed needs, not complexity.

            Args:
                name: assistant (suggestions), rag (document retrieval), automation (external actions).
            """
            def run():
                value = json.loads((ROOT / "patterns.json").read_text(encoding="utf-8"))[name]
                self.patterns[name] = value
                return {"name": name, **value}
            return record("lookup_agent_pattern", {"name": name}, run)

        @tool
        def get_code_template(name: str) -> dict:
            """Read a minimal Strands Python template, with placeholders filled by the application.

            Args:
                name: basic for no business tools; tools when business tool stubs are required.
            """
            def run():
                source = TEMPLATES[name].read_text(encoding="utf-8")
                self.templates[name] = source
                return {"name": name, "source": source, "status": "starter template, not a complete application"}
            return record("get_code_template", {"name": name}, run)

        self.tools = [retrieve_strands_docs, lookup_agent_pattern, get_code_template]
