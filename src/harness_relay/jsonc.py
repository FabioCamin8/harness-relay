"""Small JSONC reader and token-preserving edit helpers.

OpenCode configuration is JSON with comments and trailing commas.  This
module parses that grammar for conflict checks and edits only the requested
object/array members.  It never serializes the complete user document, which
keeps comments, ordering, and unrelated formatting intact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Iterable


class JsoncError(ValueError):
    """Raised for malformed JSONC or an unsafe structural edit."""


@dataclass(frozen=True)
class Token:
    kind: str
    start: int
    end: int
    value: Any = None


@dataclass
class Member:
    key: str
    key_start: int
    key_end: int
    value: "Node"
    comma: Token | None = None


@dataclass
class Node:
    kind: str
    start: int
    end: int
    value: Any = None
    members: list[Member] = field(default_factory=list)
    items: list["Node"] = field(default_factory=list)


_NUMBER = re.compile(
    r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?"
)


def parse(text: str) -> Node:
    """Parse JSONC and return a syntax tree with source ranges."""
    tokens = list(_tokens(text))
    parser = _Parser(tokens, text)
    root = parser.value()
    if parser.peek() is not None:
        token = parser.peek()
        raise JsoncError(f"unexpected token at offset {token.start}")
    return root


def find_member(node: Node, key: str) -> Member | None:
    """Find an object member without accepting duplicate-key ambiguity."""
    if node.kind != "object":
        raise JsoncError("expected an object")
    for member in node.members:
        if member.key == key:
            return member
    return None


def canonical(value: Any) -> str:
    """Return a stable comparison representation for parsed JSON values."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def edit_insert_object_member(
    text: str, node: Node, key: str, value: Any
) -> list[tuple[int, int, str]]:
    """Return an insertion edit for a missing object member."""
    if node.kind != "object":
        raise JsoncError("cannot insert an object member into a non-object")
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"))
    key_text = f"{json.dumps(key)}: {serialized}"
    close = node.end - 1
    if not node.members:
        between = text[node.start + 1 : close]
        if "\n" in between:
            indent = _child_indent(text, node, None)
            return [(close, close, f"{indent}{key_text}")]
        return [(close, close, key_text)]

    last = node.members[-1]
    between = text[last.value.end : close]
    indent = _member_indent(text, node.members[0].key_start)
    if last.comma is None and between == "":
        return [(close, close, ", " + key_text)]
    edits: list[tuple[int, int, str]] = []
    if last.comma is None:
        edits.append((last.value.end, last.value.end, ","))
    if "\n" in between:
        # Existing whitespace supplies the newline before the new member.
        prefix = "" if between.rstrip(" \t\r\n") == "" else f"\n{indent}"
        if between and between[-1] not in " \t\r\n":
            prefix = f"\n{indent}"
        edits.append((close, close, prefix + key_text))
    else:
        edits.append((close, close, " " + key_text))
    return edits


def edit_insert_array_item(
    text: str, node: Node, value: Any
) -> list[tuple[int, int, str]]:
    """Return an insertion edit for a missing array item."""
    if node.kind != "array":
        raise JsoncError("cannot insert an array item into a non-array")
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"))
    close = node.end - 1
    if not node.items:
        between = text[node.start + 1 : close]
        if "\n" in between:
            indent = _child_indent(text, node, None)
            return [(close, close, f"{indent}{serialized}")]
        return [(close, close, serialized)]

    last = node.items[-1]
    between = text[last.end : close]
    indent = _member_indent(text, node.items[0].start)
    commas = getattr(node, "commas", [])
    if (not commas or commas[-1] is None) and between == "":
        return [(close, close, ", " + serialized)]
    edits = []
    if not commas or commas[-1] is None:
        edits.append((last.end, last.end, ","))
    if "\n" in between:
        prefix = "" if between.rstrip(" \t\r\n") == "" else f"\n{indent}"
        if between and between[-1] not in " \t\r\n":
            prefix = f"\n{indent}"
        edits.append((close, close, prefix + serialized))
    else:
        edits.append((close, close, " " + serialized))
    return edits


def edit_remove_object_member(text: str, node: Node, key: str) -> list[tuple[int, int, str]]:
    """Return edits removing only one object member and its separator."""
    if node.kind != "object":
        raise JsoncError("cannot remove an object member from a non-object")
    index = next((i for i, member in enumerate(node.members) if member.key == key), None)
    if index is None:
        return []
    member = node.members[index]
    edits = [(member.key_start, member.value.end, "")]
    if index == 0:
        if member.comma is not None:
            edits.append((member.comma.start, member.comma.end, ""))
    else:
        previous = node.members[index - 1]
        if previous.comma is None:
            raise JsoncError("object member has no separator")
        edits.append((previous.comma.start, previous.comma.end, ""))
    return edits


def edit_remove_array_item(text: str, node: Node, index: int) -> list[tuple[int, int, str]]:
    """Return edits removing one array item and its separator."""
    if node.kind != "array":
        raise JsoncError("cannot remove an array item from a non-array")
    if index < 0 or index >= len(node.items):
        return []
    item = node.items[index]
    edits = [(item.start, item.end, "")]
    # The parser stores separators on the preceding item by using a synthetic
    # attribute set below.  Keeping the type generic avoids exposing tokens in
    # the public setup API.
    commas = getattr(node, "commas", [])
    if index < len(commas) and commas[index] is not None:
        edits.append((commas[index].start, commas[index].end, ""))
    elif index > 0 and commas[index - 1] is not None:
        edits.append((commas[index - 1].start, commas[index - 1].end, ""))
    elif len(node.items) > 1:
        raise JsoncError("array item has no separator")
    return edits


def apply_edits(text: str, edits: Iterable[tuple[int, int, str]]) -> str:
    """Apply non-overlapping source edits from right to left."""
    ordered = sorted(edits, key=lambda edit: (edit[0], edit[1]), reverse=True)
    previous_start = len(text) + 1
    for start, end, replacement in ordered:
        if start < 0 or end < start or end > len(text) or end > previous_start:
            raise JsoncError("overlapping or out-of-range JSONC edits")
        previous_start = start
        text = text[:start] + replacement + text[end:]
    return text


def _tokens(text: str) -> Iterable[Token]:
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if index == 0 and char == "\ufeff":
            index += 1
            continue
        if char.isspace():
            index += 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index + 2)
            index = length if newline < 0 else newline + 1
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise JsoncError(f"unterminated comment at offset {index}")
            index = end + 2
            continue
        if char in "{}[]:,":
            yield Token(char, index, index + 1, char)
            index += 1
            continue
        if char == '"':
            end = _string_end(text, index)
            raw = text[index:end]
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise JsoncError(f"invalid string at offset {index}: {exc.msg}") from exc
            yield Token("string", index, end, value)
            index = end
            continue
        number = _NUMBER.match(text, index)
        if number:
            raw = number.group(0)
            value: Any = float(raw) if any(c in raw for c in ".eE") else int(raw)
            yield Token("number", index, number.end(), value)
            index = number.end()
            continue
        for literal, value in (("true", True), ("false", False), ("null", None)):
            if text.startswith(literal, index) and _word_boundary(text, index, len(literal)):
                yield Token(literal, index, index + len(literal), value)
                index += len(literal)
                break
        else:
            raise JsoncError(f"unexpected character at offset {index}: {char!r}")


def _string_end(text: str, start: int) -> int:
    index = start + 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == '"':
            return index + 1
        if text[index] in "\r\n":
            raise JsoncError(f"newline in string at offset {start}")
        index += 1
    raise JsoncError(f"unterminated string at offset {start}")


def _word_boundary(text: str, start: int, length: int) -> bool:
    end = start + length
    return end == len(text) or not (text[end].isalnum() or text[end] == "_")


class _Parser:
    def __init__(self, tokens: list[Token], text: str) -> None:
        self.tokens = tokens
        self.text = text
        self.index = 0

    def peek(self) -> Token | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self, kind: str | None = None) -> Token:
        token = self.peek()
        if token is None:
            raise JsoncError("unexpected end of JSONC")
        if kind is not None and token.kind != kind:
            raise JsoncError(
                f"expected {kind!r} at offset {token.start}, found {token.kind!r}"
            )
        self.index += 1
        return token

    def value(self) -> Node:
        token = self.peek()
        if token is None:
            raise JsoncError("empty JSONC document")
        if token.kind == "{":
            return self.object()
        if token.kind == "[":
            return self.array()
        self.take()
        if token.kind not in {"string", "number", "true", "false", "null"}:
            raise JsoncError(f"expected a JSON value at offset {token.start}")
        return Node("primitive", token.start, token.end, token.value)

    def object(self) -> Node:
        opening = self.take("{")
        members: list[Member] = []
        seen: set[str] = set()
        while self.peek() is not None and self.peek().kind != "}":
            key = self.take("string")
            if key.value in seen:
                raise JsoncError(f"duplicate object key {key.value!r} at offset {key.start}")
            seen.add(key.value)
            self.take(":")
            value = self.value()
            comma = None
            if self.peek() is not None and self.peek().kind == ",":
                comma = self.take(",")
            members.append(Member(key.value, key.start, key.end, value, comma))
            if comma is None and self.peek() is not None and self.peek().kind != "}":
                token = self.peek()
                raise JsoncError(f"expected ',' at offset {token.start}")
        closing = self.take("}")
        return Node(
            "object",
            opening.start,
            closing.end,
            value={member.key: member.value.value for member in members},
            members=members,
        )

    def array(self) -> Node:
        opening = self.take("[")
        items: list[Node] = []
        commas: list[Token | None] = []
        while self.peek() is not None and self.peek().kind != "]":
            item = self.value()
            comma = None
            if self.peek() is not None and self.peek().kind == ",":
                comma = self.take(",")
            items.append(item)
            commas.append(comma)
            if comma is None and self.peek() is not None and self.peek().kind != "]":
                token = self.peek()
                raise JsoncError(f"expected ',' at offset {token.start}")
        closing = self.take("]")
        node = Node(
            "array",
            opening.start,
            closing.end,
            value=[item.value for item in items],
            items=items,
        )
        node.commas = commas  # type: ignore[attr-defined]
        return node


def _member_indent(text: str, position: int) -> str:
    line_start = text.rfind("\n", 0, position) + 1
    prefix = text[line_start:position]
    return prefix if prefix.strip() == "" else "  "


def _child_indent(text: str, node: Node, position: int | None) -> str:
    close_line = text.rfind("\n", 0, node.end - 1) + 1
    close_prefix = text[close_line : node.end - 1]
    base = close_prefix if close_prefix.strip() == "" else ""
    return base + "  "
