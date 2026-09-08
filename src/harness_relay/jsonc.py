"""Bounded, source-preserving JSONC operations for OpenCode configuration.

Tree-sitter supplies the structure, comments, and exact UTF-8 byte ranges.
Its JSON grammar deliberately reports trailing commas as ``ERROR`` nodes, so
this module recognizes only a comma after a complete direct member/value when
the remainder before that container's close is whitespace/comments.  The
recognized comma and comment ranges are masked in a validation copy and the
result must then parse as strict JSON.  No generic error recovery is accepted.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any, Iterable, Sequence


class JsoncError(ValueError):
    """Raised for malformed JSONC or an unsafe source edit."""


MISSING = object()

_VALUE_TYPES = frozenset(
    ("object", "array", "string", "number", "true", "false", "null")
)


@dataclass(frozen=True)
class _Document:
    source: bytes
    tree: Any
    root: Any
    value: Any
    trailing_commas: tuple[tuple[int, int, int, int], ...]


def _tree_sitter_parser() -> Any:
    """Create a parser for the pinned JSON grammar."""
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_json
    except ImportError as exc:  # pragma: no cover - packaging/environment path
        raise JsoncError(
            "JSONC setup requires the tree-sitter and tree-sitter-json "
            "dependencies; install project dependencies before editing OpenCode config"
        ) from exc
    try:
        return Parser(Language(tree_sitter_json.language()))
    except Exception as exc:  # pragma: no cover - incompatible dependency pair
        raise JsoncError(f"cannot initialize the JSONC parser: {exc}") from exc


def _parse_tree(source: bytes) -> Any:
    parser = _tree_sitter_parser()
    try:
        return parser.parse(source)
    except Exception as exc:
        raise JsoncError(f"cannot parse JSONC source: {exc}") from exc


def _walk(node: Any) -> Iterable[Any]:
    yield node
    for child in node.children:
        yield from _walk(child)


def _is_value_node(node: Any) -> bool:
    return node.type in _VALUE_TYPES and node.end_byte > node.start_byte


def _direct_values(node: Any) -> list[Any]:
    if node.type == "object":
        return [child for child in node.named_children if child.type == "pair"]
    if node.type == "array":
        return [child for child in node.named_children if _is_value_node(child)]
    return []


def _skip_trivia(source: bytes, start: int, end: int) -> int | None:
    """Return the first non-trivia byte, or ``None`` for malformed trivia."""
    index = start
    while index < end:
        byte = source[index]
        if byte in b" \t\r\n":
            index += 1
            continue
        if source.startswith(b"//", index):
            newline = source.find(b"\n", index + 2, end)
            if newline < 0:
                return end
            index = newline + 1
            continue
        if source.startswith(b"/*", index):
            close = source.find(b"*/", index + 2, end)
            if close < 0:
                return None
            index = close + 2
            continue
        return index
    return end


def _trailing_comma(source: bytes, container: Any, value: Any) -> tuple[int, int] | None:
    """Recognize one comma after a complete value before its close."""
    close = container.end_byte - 1
    after_value = _skip_trivia(source, value.end_byte, close)
    if after_value is None or after_value >= close or source[after_value] != ord(","):
        return None
    after_comma = _skip_trivia(source, after_value + 1, close)
    if after_comma != close:
        return None
    return after_value, after_value + 1


def _mask_range(masked: bytearray, source: bytes, start: int, end: int) -> None:
    """Mask a comment/range while preserving all line-ending bytes."""
    if start < 0 or end < start or end > len(source):
        raise JsoncError("parser returned an invalid source range")
    for index in range(start, end):
        if source[index] not in (ord("\r"), ord("\n")):
            masked[index] = ord(" ")


def _validation_source(
    tree: Any, source: bytes
) -> tuple[bytes, tuple[tuple[int, int, int, int], ...]]:
    masked = bytearray(source)
    trailing: list[tuple[int, int, int, int]] = []
    errors: list[Any] = []
    if source.startswith(b"\xef\xbb\xbf"):
        _mask_range(masked, source, 0, 3)
    for node in _walk(tree.root_node):
        if node.type == "ERROR":
            errors.append(node)
        if node.type == "comment":
            _mask_range(masked, source, node.start_byte, node.end_byte)
        elif node.type in {"object", "array"}:
            for value in _direct_values(node):
                candidate = _trailing_comma(source, node, value)
                if candidate is not None:
                    trailing.append((node.start_byte, node.end_byte, *candidate))
                    _mask_range(masked, source, *candidate)
    for error in errors:
        if not any(
            error.start_byte == start and error.end_byte == end
            for _, _, start, end in trailing
        ):
            raise JsoncError(
                "unrecognized JSONC parser recovery at byte "
                f"{error.start_byte}"
            )
    return bytes(masked), tuple(trailing)


def _duplicate_check(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise JsoncError(f"duplicate object key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise JsoncError(f"non-JSON numeric constant {value!r}")


def _strict_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise JsoncError(f"non-finite JSON number {value!r}")
    return result


def _validated(text: str) -> _Document:
    if not isinstance(text, str):
        raise JsoncError("JSONC source must be text")
    source = text.encode("utf-8")
    tree = _parse_tree(source)
    masked, trailing = _validation_source(tree, source)
    try:
        validation_text = masked.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise JsoncError(f"JSONC source is not valid UTF-8: {exc}") from exc
    try:
        value = json.loads(
            validation_text,
            object_pairs_hook=_duplicate_check,
            parse_constant=_reject_constant,
            parse_float=_strict_float,
        )
    except JsoncError:
        raise
    except json.JSONDecodeError as exc:
        raise JsoncError(
            f"invalid JSONC at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except (TypeError, ValueError) as exc:
        raise JsoncError(f"invalid JSONC: {exc}") from exc
    root = tree.root_node
    root_value = next(
        (child for child in root.named_children if _is_value_node(child)),
        None,
    )
    if root_value is None:
        raise JsoncError("empty JSONC document")
    return _Document(source, tree, root_value, value, trailing)


def parse(text: str) -> Any:
    """Parse valid JSONC into ordinary Python values after policy checks."""
    return _validated(text).value


def canonical(value: Any) -> str:
    """Return a stable comparison representation for parsed JSON values."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_text(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(", ", ": "),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise JsoncError(f"cannot serialize JSON value: {exc}") from exc


def _key_value(pair: Any, source: bytes) -> str:
    key = pair.child_by_field_name("key")
    if key is None or key.type != "string":
        raise JsoncError("object member has no complete string key")
    try:
        value = json.loads(source[key.start_byte : key.end_byte].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JsoncError("object member key is not a valid JSON string") from exc
    if not isinstance(value, str):
        raise JsoncError("object member key is not a string")
    return value


def _object_pairs(node: Any) -> list[Any]:
    return [child for child in node.named_children if child.type == "pair"]


def _array_values(node: Any) -> list[Any]:
    return [child for child in node.named_children if _is_value_node(child)]


def _resolve_node(document: _Document, path: Sequence[str | int]) -> Any | None:
    node = document.root
    for segment in path:
        if node.type == "object" and isinstance(segment, str):
            match = None
            for pair in _object_pairs(node):
                if _key_value(pair, document.source) == segment:
                    match = pair.child_by_field_name("value")
                    break
            if match is None:
                return None
            node = match
        elif node.type == "array" and type(segment) is int:
            values = _array_values(node)
            if segment < 0 or segment >= len(values):
                return None
            node = values[segment]
        else:
            return None
    return node


def _apply_byte_edits(source: bytes, edits: Iterable[tuple[int, int, bytes]]) -> str:
    ordered = sorted(edits, key=lambda edit: (edit[0], edit[1]), reverse=True)
    previous_start = len(source) + 1
    result = source
    for start, end, replacement in ordered:
        if start < 0 or end < start or end > len(source) or end > previous_start:
            raise JsoncError("overlapping or out-of-range JSONC edits")
        if not isinstance(replacement, bytes):
            raise JsoncError("JSONC replacement must be UTF-8 bytes")
        result = result[:start] + replacement + result[end:]
        previous_start = start
    try:
        return result.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise JsoncError(f"JSONC edit produced invalid UTF-8: {exc}") from exc


def _validated_edit(document: _Document, edits: Iterable[tuple[int, int, bytes]]) -> str:
    result = _apply_byte_edits(document.source, edits)
    _validated(result)
    return result


def _line_start(source: bytes, position: int) -> int:
    return source.rfind(b"\n", 0, position) + 1


def _newline(source: bytes) -> bytes:
    return b"\r\n" if b"\r\n" in source else b"\n"


def _line_indent(source: bytes, position: int) -> bytes:
    start = _line_start(source, position)
    prefix = source[start:position]
    return prefix if all(byte in b" \t" for byte in prefix) else b""


def _child_indent(document: _Document, container: Any) -> bytes:
    values = _direct_values(container)
    if values:
        indent = _line_indent(document.source, values[0].start_byte)
        if indent or b"\n" in document.source[container.start_byte : container.end_byte]:
            return indent
    close_indent = _line_indent(document.source, container.end_byte - 1)
    if close_indent or b"\n" in document.source[container.start_byte : container.end_byte]:
        return close_indent + b"  "
    return b"  "


def _multiline_close(document: _Document, container: Any) -> tuple[int, bytes] | None:
    close = container.end_byte - 1
    line_start = _line_start(document.source, close)
    indent = _line_indent(document.source, close)
    if line_start > container.start_byte and document.source[line_start:close] == indent:
        return line_start, indent
    return None


def _trailing_for(document: _Document, container: Any) -> tuple[int, int] | None:
    candidates = [
        (comma_start, comma_end)
        for container_start, container_end, comma_start, comma_end
        in document.trailing_commas
        if container_start == container.start_byte
        and container_end == container.end_byte
    ]
    if not candidates:
        return None
    return max(candidates)


def _append_value(document: _Document, container: Any, value: Any) -> str:
    serialized = _json_text(value)
    close = container.end_byte - 1
    existing = _direct_values(container)
    trailing = _trailing_for(document, container)
    edits: list[tuple[int, int, bytes]] = []
    multiline = _multiline_close(document, container)
    if multiline is not None:
        line_start, _ = multiline
        if existing and trailing is None:
            edits.append((existing[-1].end_byte, existing[-1].end_byte, b","))
        edits.append(
            (
                line_start,
                line_start,
                _child_indent(document, container) + serialized + _newline(document.source),
            )
        )
    elif existing:
        edits.append((close, close, (b"" if trailing else b", ") + serialized))
    else:
        edits.append((close, close, serialized))
    return _validated_edit(document, edits)


def _insert_object_member(document: _Document, container: Any, key: str, value: Any) -> str:
    serialized = _json_text(value)
    member = json.dumps(key, ensure_ascii=False).encode("utf-8") + b": " + serialized
    close = container.end_byte - 1
    existing = _object_pairs(container)
    trailing = _trailing_for(document, container)
    edits: list[tuple[int, int, bytes]] = []
    multiline = _multiline_close(document, container)
    if multiline is not None:
        line_start, _ = multiline
        if existing and trailing is None:
            edits.append((existing[-1].end_byte, existing[-1].end_byte, b","))
        edits.append(
            (
                line_start,
                line_start,
                _child_indent(document, container) + member + _newline(document.source),
            )
        )
    elif existing:
        edits.append((close, close, (b"" if trailing else b", ") + member))
    else:
        edits.append((close, close, member))
    return _validated_edit(document, edits)


def edit(text: str, path: Sequence[str | int], value: Any) -> str:
    """Set one object property/array value with source-preserving edits."""
    document = _validated(text)
    if not path:
        raise JsoncError("editing the JSONC document root is not supported")
    parent = _resolve_node(document, path[:-1])
    if parent is None:
        raise JsoncError("cannot edit missing JSONC parent path")
    segment = path[-1]
    if parent.type == "object" and isinstance(segment, str):
        for pair in _object_pairs(parent):
            if _key_value(pair, document.source) == segment:
                target = pair.child_by_field_name("value")
                if target is None:
                    raise JsoncError("object member has no complete value")
                return _validated_edit(
                    document,
                    [(target.start_byte, target.end_byte, _json_text(value))],
                )
        return _insert_object_member(document, parent, segment, value)
    if parent.type == "array" and type(segment) is int:
        values = _array_values(parent)
        if segment < 0 or segment > len(values):
            raise JsoncError(f"array index {segment} is out of range")
        if segment == len(values):
            return _append_value(document, parent, value)
        return _validated_edit(
            document,
            [(values[segment].start_byte, values[segment].end_byte, _json_text(value))],
        )
    raise JsoncError("JSONC edit path must target an object property or array index")


def _direct_commas(node: Any) -> list[tuple[int, int]]:
    return [
        (child.start_byte, child.end_byte)
        for child in node.children
        if child.type == ","
    ]


def _remove_member(document: _Document, container: Any, target: Any) -> str:
    members = _object_pairs(container)
    index = members.index(target)
    edits: list[tuple[int, int, bytes]] = [(target.start_byte, target.end_byte, b"")]
    commas = _direct_commas(container)
    next_member = members[index + 1] if index + 1 < len(members) else None
    if next_member is not None:
        following = [
            comma
            for comma in commas
            if target.end_byte <= comma[0] < next_member.start_byte
        ]
        if following:
            edits.append((following[0][0], following[0][1], b""))
    else:
        trailing = _trailing_for(document, container)
        if trailing is not None:
            edits.append((trailing[0], trailing[1], b""))
        else:
            preceding = [comma for comma in commas if comma[1] <= target.start_byte]
            if preceding:
                edits.append((preceding[-1][0], preceding[-1][1], b""))
    return _validated_edit(document, edits)


def _remove_item(document: _Document, container: Any, target: Any) -> str:
    values = _array_values(container)
    index = values.index(target)
    edits: list[tuple[int, int, bytes]] = [(target.start_byte, target.end_byte, b"")]
    commas = _direct_commas(container)
    next_value = values[index + 1] if index + 1 < len(values) else None
    if next_value is not None:
        following = [
            comma
            for comma in commas
            if target.end_byte <= comma[0] < next_value.start_byte
        ]
        if following:
            edits.append((following[0][0], following[0][1], b""))
    else:
        trailing = _trailing_for(document, container)
        if trailing is not None:
            edits.append((trailing[0], trailing[1], b""))
        else:
            preceding = [comma for comma in commas if comma[1] <= target.start_byte]
            if preceding:
                edits.append((preceding[-1][0], preceding[-1][1], b""))
    return _validated_edit(document, edits)


def remove(text: str, path: Sequence[str | int]) -> str:
    """Remove one object property or array value, preserving surrounding text."""
    document = _validated(text)
    if not path:
        raise JsoncError("removing the JSONC document root is not supported")
    parent = _resolve_node(document, path[:-1])
    if parent is None:
        raise JsoncError("cannot remove missing JSONC parent path")
    segment = path[-1]
    if parent.type == "object" and isinstance(segment, str):
        for pair in _object_pairs(parent):
            if _key_value(pair, document.source) == segment:
                return _remove_member(document, parent, pair)
        return text
    if parent.type == "array" and type(segment) is int:
        values = _array_values(parent)
        if segment < 0 or segment >= len(values):
            return text
        return _remove_item(document, parent, values[segment])
    raise JsoncError("JSONC removal path must target an object property or array index")


def source_fragment(text: str, path: Sequence[str | int]) -> str | None:
    """Return the exact UTF-8 source fragment for an object or array value."""
    document = _validated(text)
    if not path:
        return None
    parent = _resolve_node(document, path[:-1])
    if parent is None:
        return None
    segment = path[-1]
    if parent.type == "object" and isinstance(segment, str):
        for pair in _object_pairs(parent):
            if _key_value(pair, document.source) == segment:
                node = pair
                break
        else:
            return None
    elif parent.type == "array" and type(segment) is int:
        values = _array_values(parent)
        if segment < 0 or segment >= len(values):
            return None
        node = values[segment]
    else:
        return None
    try:
        return document.source[node.start_byte : node.end_byte].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise JsoncError("JSONC source fragment is not valid UTF-8") from exc
