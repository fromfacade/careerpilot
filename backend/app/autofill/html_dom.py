"""Small HTML tree for form controls. Ignores CSS class names."""

from __future__ import annotations

from html.parser import HTMLParser

_VOID = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)
_SKIP_TEXT = frozenset({"script", "style", "noscript"})


class Node:
    def __init__(self, tag: str, attrs: list[tuple[str, str | None]]):
        self.tag = tag
        self.attrs = {key.casefold(): value or "" for key, value in attrs}
        self.parent: Node | None = None
        self.events: list[tuple[str, object]] = []

    def get(self, name: str) -> str:
        return self.attrs.get(name, "")

    def has(self, name: str) -> bool:
        return name in self.attrs


class _Builder(HTMLParser):
    def __init__(self, root: Node):
        super().__init__(convert_charrefs=True)
        self.root = root
        self.stack = [root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag.casefold(), attrs)
        node.parent = self.stack[-1]
        self.stack[-1].events.append(("el", node))
        if tag.casefold() not in _VOID:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        wanted = tag.casefold()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == wanted:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if self.stack[-1].tag in _SKIP_TEXT:
            return
        if data:
            self.stack[-1].events.append(("text", data))


def parse_html(html: str) -> Node:
    root = Node("document", [])
    builder = _Builder(root)
    builder.feed(html or "")
    builder.close()
    return root


def text_of(node: Node) -> str:
    parts: list[str] = []

    def walk(current: Node) -> None:
        for kind, value in current.events:
            if kind == "text":
                parts.append(str(value))
            else:
                walk(value)  # type: ignore[arg-type]

    walk(node)
    return " ".join("".join(parts).split())


def walk(node: Node):
    for kind, value in node.events:
        if kind == "el":
            yield value
            yield from walk(value)  # type: ignore[arg-type]


def by_id(root: Node) -> dict[str, Node]:
    found: dict[str, Node] = {}
    for node in walk(root):
        element_id = node.get("id")
        if element_id and element_id not in found:
            found[element_id] = node
    return found
