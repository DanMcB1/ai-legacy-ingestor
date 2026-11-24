"""Parse a COBOL copybook and decode a fixed-width EBCDIC / COMP-3 file.

This is a small, deliberate subset of COBOL — enough to show a Forward
Deployed Engineer what "the mainframe export" actually looks like:

- ``PIC X`` / ``PIC 9`` display fields, encoded in EBCDIC (CP037)
- ``PIC S9(n)V99 COMP-3`` packed-decimal amounts
- ``REDEFINES`` (same offset as the named field, does not grow the record)
- ``OCCURS n TIMES`` repeating groups

It is not a full COBOL compiler. Comments, a typical 01-level record, and
the clauses above are what this demo supports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

# US IBM mainframe EBCDIC. Spaces are 0x40; digits are 0xF0-0xF9.
EBCDIC = "cp037"

# Packed-decimal sign nibbles (IBM). C/A/E/F = positive; D/B = negative.
_POS_SIGNS = {0xA, 0xC, 0xE, 0xF}
_NEG_SIGNS = {0xB, 0xD}


@dataclass
class Pic:
    """A parsed PICTURE clause."""

    raw: str
    kind: str  # "X" or "9"
    signed: bool
    integer_digits: int
    scale: int  # digits after the implied decimal (V)
    comp3: bool

    @property
    def digit_count(self) -> int:
        return self.integer_digits + self.scale

    @property
    def byte_length(self) -> int:
        if self.comp3:
            # Digits plus a sign nibble, rounded up to a whole byte.
            return (self.digit_count + 2) // 2
        return self.digit_count


@dataclass
class FieldDef:
    name: str
    level: int
    pic: Pic | None = None
    occurs: int = 1
    redefines: str | None = None
    offset: int = 0
    length: int = 0
    children: list[FieldDef] = field(default_factory=list)

    @property
    def is_group(self) -> bool:
        return self.pic is None and bool(self.children)


@dataclass
class Copybook:
    name: str
    record: FieldDef
    record_length: int
    encoding: str = EBCDIC

    def fields(self) -> list[FieldDef]:
        out: list[FieldDef] = []

        def walk(node: FieldDef) -> None:
            out.append(node)
            for child in node.children:
                walk(child)

        walk(self.record)
        return out


class CopybookError(ValueError):
    """The copybook could not be parsed, or a record could not be decoded."""


_PIC_TOKEN = re.compile(
    r"PIC(?:TURE)?\s+(S)?([9XA]+(?:\(\d+\))?(?:V(?:[9]+(?:\(\d+\))?)?)?)",
    re.IGNORECASE,
)
_COMP3 = re.compile(r"\b(?:COMP(?:UTATIONAL)?-3|PACKED-DECIMAL)\b", re.IGNORECASE)
_OCCURS = re.compile(r"\bOCCURS\s+(\d+)\s+TIMES\b", re.IGNORECASE)
_REDEFINES = re.compile(r"\bREDEFINES\s+([A-Z0-9][A-Z0-9-]*)", re.IGNORECASE)
_LEVEL = re.compile(
    r"^\s*(\d{1,2})\s+([A-Z0-9][A-Z0-9-]*|FILLER)\b(.*)$",
    re.IGNORECASE,
)


def _count_pic_digits(part: str) -> tuple[str, int]:
    """Return (kind, count) for one side of a V (e.g. '9(9)', 'XXX', '99')."""
    if not part:
        return "9", 0
    kind = "X" if re.search(r"[XA]", part, re.IGNORECASE) else "9"
    total = 0
    for match in re.finditer(r"([9XA])(?:\((\d+)\))?", part, re.IGNORECASE):
        total += int(match.group(2) or 1)
    return kind, total


def parse_pic(clause: str, comp3: bool = False) -> Pic:
    text = clause.strip().replace(" ", "").upper()
    signed = text.startswith("S")
    if signed:
        text = text[1:]
    if "V" in text:
        left, right = text.split("V", 1)
    else:
        left, right = text, ""
    kind, integer_digits = _count_pic_digits(left)
    _, scale = _count_pic_digits(right)
    if kind == "X" and (signed or scale or comp3):
        raise CopybookError(f"PIC {clause} cannot be signed, have a V, or be COMP-3")
    if integer_digits + scale == 0:
        raise CopybookError(f"Could not parse PIC {clause}")
    return Pic(
        raw=clause,
        kind=kind,
        signed=signed,
        integer_digits=integer_digits,
        scale=scale,
        comp3=comp3,
    )


def _strip_comment(line: str) -> str:
    """Drop a COBOL comment line, or a trailing comment after a period."""
    if not line:
        return ""
    # Fixed-format: a '*' or '/' in column 7 is a comment.
    if len(line) >= 7 and line[6] in {"*", "/"} and line[:6].strip() == "":
        return ""
    stripped = line.strip()
    if stripped.startswith("*") or stripped.startswith("*>"):
        return ""
    return line.rstrip("\n")


def _logical_lines(text: str) -> Iterable[str]:
    """Join continuation lines (a clause that has not yet hit a period)."""
    buf = ""
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if not line.strip():
            continue
        # Ignore sequence numbers / identification area if they look like 1-6 digits.
        if len(line) > 6 and line[:6].strip().isdigit() and line[6] in {" ", "*"}:
            if line[6] == "*":
                continue
            line = line[6:72] if len(line) > 72 else line[6:]
        buf = f"{buf} {line.strip()}".strip()
        if buf.endswith("."):
            yield buf[:-1].strip()
            buf = ""
    if buf:
        yield buf.strip()


def parse_copybook(text: str, name: str = "RECORD") -> Copybook:
    """Parse copybook source into a layout with byte offsets."""
    nodes: list[FieldDef] = []
    for clause in _logical_lines(text):
        match = _LEVEL.match(clause)
        if not match:
            continue
        level = int(match.group(1))
        field_name = match.group(2).upper().replace("-", "_")
        rest = match.group(3) or ""
        occurs = 1
        occurs_match = _OCCURS.search(rest)
        if occurs_match:
            occurs = int(occurs_match.group(1))
        redefines = None
        redef_match = _REDEFINES.search(rest)
        if redef_match:
            redefines = redef_match.group(1).upper().replace("-", "_")
        pic = None
        pic_match = _PIC_TOKEN.search(rest)
        if pic_match:
            signed = bool(pic_match.group(1))
            pic_body = (("S" if signed else "") + pic_match.group(2))
            pic = parse_pic(pic_body, comp3=bool(_COMP3.search(rest)))
        nodes.append(
            FieldDef(
                name=field_name,
                level=level,
                pic=pic,
                occurs=occurs,
                redefines=redefines,
            )
        )
    if not nodes:
        raise CopybookError("No COBOL field definitions were found in the copybook")

    root = nodes[0]
    stack = [root]
    for node in nodes[1:]:
        while stack and stack[-1].level >= node.level:
            stack.pop()
        if not stack:
            raise CopybookError(f"Field {node.name} has no parent group")
        stack[-1].children.append(node)
        stack.append(node)

    by_name: dict[str, FieldDef] = {}

    def compute(node: FieldDef, offset: int) -> int:
        """Assign offsets and return the end offset (span) of this node."""
        if node.redefines:
            target = by_name.get(node.redefines)
            if target is None:
                raise CopybookError(f"{node.name} REDEFINES unknown field {node.redefines}")
            offset = target.offset
        node.offset = offset
        if node.children:
            cursor = offset
            end = offset
            for child in node.children:
                child_end = compute(child, cursor)
                if child.redefines:
                    end = max(end, child_end)
                    # Do not advance cursor: the next sibling continues after
                    # the original (redefined) field, not after this view.
                else:
                    cursor = child_end
                    end = max(end, child_end)
            element_length = end - offset
        elif node.pic is not None:
            element_length = node.pic.byte_length
        else:
            element_length = 0
        node.length = element_length * node.occurs
        by_name[node.name] = node
        if node.redefines:
            return offset + node.length
        return offset + node.length

    compute(root, 0)
    return Copybook(name=root.name or name, record=root, record_length=root.length)


def load_copybook(path: str | Path) -> Copybook:
    return parse_copybook(Path(path).read_text(encoding="utf-8"), name=Path(path).stem)


# ---------------------------------------------------------------------------
# Packed decimal (COMP-3)
# ---------------------------------------------------------------------------


def encode_comp3(value: Decimal | int | float | str, pic: Pic) -> bytes:
    """Encode a number as IBM packed decimal for the given PIC."""
    if not pic.comp3:
        raise CopybookError("encode_comp3 called on a non-COMP-3 PIC")
    amount = Decimal(str(value))
    negative = amount < 0
    digits_value = abs(amount).scaleb(pic.scale)
    try:
        as_int = int(digits_value.to_integral_value())
    except (InvalidOperation, ValueError) as exc:
        raise CopybookError(f"Cannot pack {value} as {pic.raw}") from exc
    # If the Decimal had a fractional leftover after scaling, refuse it.
    if digits_value != Decimal(as_int):
        raise CopybookError(f"Value {value} has more than {pic.scale} decimal places")
    rendered = f"{as_int:0{pic.digit_count}d}"
    if len(rendered) > pic.digit_count:
        raise CopybookError(f"Value {value} overflows PIC {pic.raw}")
    sign = 0xD if negative else (0xC if pic.signed else 0xF)
    nibbles = [int(ch) for ch in rendered]
    # An odd number of digits already fills the bytes with the sign; an even
    # number of digits needs a leading 0 nibble so the sign sits in the last half.
    if (len(nibbles) + 1) % 2 == 1:
        nibbles.insert(0, 0)
    nibbles.append(sign)
    out = bytearray()
    for i in range(0, len(nibbles), 2):
        out.append((nibbles[i] << 4) | nibbles[i + 1])
    if len(out) != pic.byte_length:
        raise CopybookError(
            f"Packed length mismatch for {pic.raw}: got {len(out)}, expected {pic.byte_length}"
        )
    return bytes(out)


def decode_comp3(data: bytes, pic: Pic) -> Decimal:
    """Decode IBM packed decimal into a Decimal."""
    if not data:
        raise CopybookError("Empty COMP-3 field")
    nibbles: list[int] = []
    for byte in data:
        nibbles.append((byte >> 4) & 0x0F)
        nibbles.append(byte & 0x0F)
    sign = nibbles[-1]
    digits = nibbles[:-1]
    if any(d > 9 for d in digits):
        raise CopybookError("Invalid packed-decimal digit")
    if sign not in _POS_SIGNS and sign not in _NEG_SIGNS:
        raise CopybookError(f"Invalid packed-decimal sign nibble {sign:#x}")
    number = 0
    for digit in digits:
        number = number * 10 + digit
    value = Decimal(number).scaleb(-pic.scale)
    if sign in _NEG_SIGNS:
        value = -value
    return value


# ---------------------------------------------------------------------------
# Record encode / decode
# ---------------------------------------------------------------------------


def _pad(text: str, length: int) -> str:
    if len(text) > length:
        return text[:length]
    return text.ljust(length)


def _encode_leaf(pic: Pic, value: Any) -> bytes:
    if pic.comp3:
        if value in (None, ""):
            value = Decimal("0")
        return encode_comp3(value, pic)
    if pic.kind == "9":
        if value in (None, ""):
            number = 0
        else:
            amount = Decimal(str(value))
            number = int(abs(amount).scaleb(pic.scale))
        rendered = f"{number:0{pic.digit_count}d}"
        if len(rendered) > pic.digit_count:
            raise CopybookError(f"Value {value} overflows PIC {pic.raw}")
        return rendered.encode(EBCDIC)
    text = "" if value is None else str(value)
    return _pad(text, pic.digit_count).encode(EBCDIC)


def _decode_leaf(pic: Pic, data: bytes) -> Any:
    if pic.comp3:
        return decode_comp3(data, pic)
    text = data.decode(EBCDIC)
    if pic.kind == "9":
        digits = text.strip() or "0"
        if not re.fullmatch(r"-?\d+", digits):
            raise CopybookError(f"Non-numeric display field: {text!r}")
        number = Decimal(digits)
        if pic.scale:
            number = number.scaleb(-pic.scale)
        return int(number) if pic.scale == 0 else number
    return text.rstrip()


def _element_length(node: FieldDef) -> int:
    if node.occurs <= 1:
        return node.length
    return node.length // node.occurs


def _read_value(node: FieldDef, record: bytes) -> Any:
    element = _element_length(node)

    def one(at: int) -> Any:
        if node.children:
            payload: dict[str, Any] = {}
            for child in node.children:
                payload[child.name] = _read_value_from(child, record, at)
            return payload
        if node.pic is None:
            return None
        slice_ = record[at : at + node.pic.byte_length]
        if len(slice_) < node.pic.byte_length:
            raise CopybookError(
                f"{node.name} truncated at offset {at} "
                f"(need {node.pic.byte_length} bytes, have {len(slice_)})"
            )
        return _decode_leaf(node.pic, slice_)

    def _read_value_from(child: FieldDef, rec: bytes, base: int) -> Any:
        # Child offsets are absolute from the start of the 01-level record
        # when occurs == 1, but inside an OCCURS parent they need to be
        # relocated relative to this occurrence.
        return _read_at(child, rec, shift=base - node.offset)

    if node.occurs > 1:
        return [one(node.offset + i * element) for i in range(node.occurs)]
    return one(node.offset)


def _read_at(node: FieldDef, record: bytes, shift: int = 0) -> Any:
    element = _element_length(node)
    base = node.offset + shift

    def one(at: int) -> Any:
        if node.children:
            return {child.name: _read_at(child, record, shift=at - node.offset) for child in node.children}
        if node.pic is None:
            return None
        slice_ = record[at : at + node.pic.byte_length]
        if len(slice_) < node.pic.byte_length:
            raise CopybookError(
                f"{node.name} truncated at offset {at} "
                f"(need {node.pic.byte_length} bytes, have {len(slice_)})"
            )
        return _decode_leaf(node.pic, slice_)

    if node.occurs > 1:
        return [one(base + i * element) for i in range(node.occurs)]
    return one(base)


def decode_record(book: Copybook, data: bytes) -> dict[str, Any]:
    """Decode one fixed-width record into a dictionary of field values."""
    if len(data) < book.record_length:
        raise CopybookError(
            f"Record is {len(data)} bytes, copybook expects {book.record_length}"
        )
    data = data[: book.record_length]
    out: dict[str, Any] = {}
    for child in book.record.children:
        if child.name == "FILLER":
            continue
        out[child.name] = _read_at(child, data, shift=0)
    return out


def _write_leaf(record: bytearray, node: FieldDef, value: Any, shift: int = 0) -> None:
    at = node.offset + shift
    if node.pic is None:
        return
    encoded = _encode_leaf(node.pic, value)
    record[at : at + len(encoded)] = encoded


def _write_at(record: bytearray, node: FieldDef, value: Any, shift: int = 0) -> None:
    if node.name == "FILLER" and not node.children:
        return
    # A REDEFINES view occupies the same bytes as the original field.
    # Do not blank it out when the caller only supplied the original name.
    if node.redefines and value is None:
        return
    element = _element_length(node)
    base = node.offset + shift
    if node.occurs > 1:
        items = list(value or [])
        for i in range(node.occurs):
            item = items[i] if i < len(items) else None
            _write_occurrence(record, node, item, base + i * element)
        return
    _write_occurrence(record, node, value, base)


def _write_occurrence(record: bytearray, node: FieldDef, value: Any, at: int) -> None:
    if node.children:
        mapping = value or {}
        for child in node.children:
            child_shift = at - node.offset
            _write_at(record, child, (mapping or {}).get(child.name), shift=child_shift)
        return
    # Reposition write: _write_leaf uses node.offset + shift = at, so shift = at - node.offset
    _write_leaf(record, node, value, shift=at - node.offset)


def encode_record(book: Copybook, values: dict[str, Any]) -> bytes:
    """Encode a dictionary of field values into one fixed-width EBCDIC record."""
    record = bytearray(b"\x40" * book.record_length)  # EBCDIC spaces
    for child in book.record.children:
        _write_at(record, child, values.get(child.name), shift=0)
    return bytes(record)


def decode_file(
    book: Copybook, data: bytes
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a binary file into records.

    Returns ``(ok_rows, rejects)``. A short trailing chunk or a record that
    fails COMP-3 / display decoding is a reject, not a crash.
    """
    ok: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    length = book.record_length
    if length <= 0:
        raise CopybookError("Copybook record length is 0")
    offset = 0
    number = 0
    while offset < len(data):
        number += 1
        chunk = data[offset : offset + length]
        offset += length
        if len(chunk) < length:
            rejects.append(
                {
                    "record_number": number,
                    "reason": (
                        f"Truncated record: {len(chunk)} bytes, "
                        f"copybook expects {length}"
                    ),
                    "offset": offset - len(chunk),
                }
            )
            break
        try:
            row = decode_record(book, chunk)
            row["_record_number"] = number
            ok.append(row)
        except CopybookError as exc:
            rejects.append(
                {
                    "record_number": number,
                    "reason": str(exc),
                    "offset": offset - length,
                }
            )
    return ok, rejects


def encode_file(book: Copybook, rows: Iterable[dict[str, Any]]) -> bytes:
    return b"".join(encode_record(book, row) for row in rows)
