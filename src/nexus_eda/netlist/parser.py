# SPDX-License-Identifier: Apache-2.0
"""KiCad netlist parser for extracting structured data from S-expression format.

This module provides:
    - NetlistParser: Parse KiCad .net files into structured data
    - DesignRuleChecker: Basic DRC validation rules
    - NetlistData: Dataclass holding parsed netlist contents

The parser uses a recursive-descent tokenizer that correctly handles the
S-expression format used by KiCad .net (netlist) files.  Unlike regex-based
approaches, the tokenizer is immune to issues with quoted strings containing
parens, colons, or spaces — all of which appear in real KiCad exports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Node:
    """A single pin-to-net connection.

    Attributes:
        ref: Component reference designator (e.g. ``"R1"``).
        pin: Pin number/text (e.g. ``"1"`` or ``"AVCC"``).
    """

    ref: str
    pin: str

    def __str__(self) -> str:
        return f"{self.ref}/{self.pin}"

    def __repr__(self) -> str:
        return f"Node(ref={self.ref!r}, pin={self.pin!r})"


@dataclass
class Net:
    """A single net in the design.

    Attributes:
        code: Integer net code from the KiCad file (may be 0 for the
            unnamed/default net).
        name: Net name (may be empty string for the unnamed net).
        nodes: List of connected pin nodes.
    """

    code: int = 0
    name: str = ""
    nodes: List[Node] = field(default_factory=list)

    def node_ids(self) -> List[str]:
        """Return node identifiers in ``"ref/pin"`` string form."""
        return [str(n) for n in self.nodes]

    def __repr__(self) -> str:
        return f"Net(code={self.code}, name={self.name!r}, nodes={len(self.nodes)})"


@dataclass
class Component:
    """A single component in the design.

    Attributes:
        ref: Reference designator (e.g. ``"R1"``).
        fields: Dict of field name → string value.
    """

    ref: str
    fields: Dict[str, str] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"Component(ref={self.ref!r}, fields={len(self.fields)})"

    # -- convenience accessors ------------------------------------------------

    @property
    def value(self) -> Optional[str]:
        """Return the ``Value`` field if present."""
        return self._get_field("Value", "value")

    @property
    def footprint(self) -> Optional[str]:
        """Return the ``Footprint`` field if present."""
        return self._get_field("Footprint", "footprint")

    def _get_field(self, *names: str) -> Optional[str]:
        """Case-insensitive field lookup trying each candidate name."""
        for n in names:
            for key, val in self.fields.items():
                if key.lower() == n.lower():
                    return val
        return None

    def get(self, field_name: str, default: Optional[str] = None) -> Optional[str]:
        """Case-insensitive field lookup."""
        return self._get_field(field_name, default)  # type: ignore[arg-type]

    def to_dict(self) -> Dict[str, str]:
        """Return a copy of the fields dict."""
        return dict(self.fields)


@dataclass
class NetlistData:
    """Structured representation of a parsed KiCad netlist.

    The high-level collections (``.components`` dict and ``.nets`` dict) are
    preserved for backward compatibility with the original parser API,
    while the richer typed lists (``.components_list`` / ``.nets_list``) provide
    full structured access.

    Attributes:
        version: Netlist format version string.
        components: Backward-compatible dict  {ref: {field_name: value}}.
        nets: Backward-compatible dict  {net_name: ["ref/pin", ...]}.
        components_list: Typed list of :class:`Component` objects.
        nets_list: Typed list of :class:`Net` objects.
    """

    version: str = ""
    components: Dict[str, Dict] = field(default_factory=dict)
    nets: Dict[str, List[str]] = field(default_factory=dict)
    components_list: List[Component] = field(default_factory=list)
    nets_list: List[Net] = field(default_factory=list)

    # -- backward-compatible helpers ------------------------------------------

    def find_component(self, ref: str) -> Optional[Component]:
        """Look up a component by reference designator."""
        for c in self.components_list:
            if c.ref == ref:
                return c
        return None

    def find_net(self, name: str) -> Optional[Net]:
        """Look up a net by name.

        For the unnamed (code-only) net the backwards-compatible lookup
        key is ``f"#{code}"`` — this method accepts that form too.
        """
        for n in self.net_list:
            if n.name == name:
                return n
            # Allow lookup by the computed "#code" key for unnamed nets
            if not n.name and name == f"#{n.code}":
                return n
        return None

    def find_net_by_code(self, code: int) -> Optional[Net]:
        """Look up a net by numeric code."""
        for n in self.net_list:
            if n.code == code:
                return n
        return None

    @property
    def net_list(self) -> List[Net]:
        return self.nets_list

    # -- query API for connections -------------------------------------------

    def get_net_connections(self, net_name: str) -> List[Node]:
        """Return all pin nodes connected to a net by name.

        Args:
            net_name: Net name (or ``"#<code>"`` for unnamed nets).

        Returns:
            List of :class:`Node` objects, or an empty list if the net
            is not found.
        """
        net = self.find_net(net_name)
        if net is None:
            return []
        return list(net.nodes)

    def get_component_connections(self, ref: str) -> List[str]:
        """Return the names of all nets that a component is connected to.

        Args:
            ref: Component reference designator (e.g. ``"U1"``).

        Returns:
            List of net names. A net may appear more than once if the
            component has multiple pins on it.
        """
        results: List[str] = []
        for net in self.nets_list:
            for node in net.nodes:
                if node.ref == ref:
                    net_id = net.name if net.name else f"#{net.code}"
                    results.append(net_id)
        return results

    def get_connections(self) -> List[tuple]:
        """Return a flat list of all (net_name, ref, pin) connections.

        Each tuple is ``(net_name, component_ref, pin_number)``.
        Unnamed nets use ``"#" + str(code)`` as the identifier.
        """
        connections: List[tuple] = []
        for net in self.nets_list:
            net_id = net.name if net.name else f"#{net.code}"
            for node in net.nodes:
                connections.append((net_id, node.ref, node.pin))
        return connections

    def to_dict(self) -> dict:
        """Serialize to a plain dict (for JSON export)."""
        return {
            "version": self.version,
            "components": [
                {"ref": c.ref, "fields": c.to_dict()}
                for c in self.components_list
            ],
            "nets": [
                {"code": n.code, "name": n.name, "nodes": n.node_ids()}
                for n in self.nets_list
            ],
        }


@dataclass
class ValidationResult:
    """Result of a DRC check.

    Attributes:
        rule_id: Unique identifier for the DRC rule
        description: Human-readable description of the violation
        severity: 'error', 'warning', or 'info'
        component: Reference to offending component (if applicable)
        net: Name of net involved (if applicable)
        details: Free-form additional details
    """

    rule_id: str
    description: str
    severity: str  # 'error', 'warning', 'info'
    component: Optional[str] = None
    net: Optional[str] = None
    details: Optional[str] = None


# ---------------------------------------------------------------------------
# S-expression tokenizer
# ---------------------------------------------------------------------------

# Token kind constants
_TOK_LPAREN = "LPAREN"
_TOK_RPAREN = "RPAREN"
_TOK_ATOM = "ATOM"
_TOK_STRING = "STRING"


@dataclass
class _Token:
    kind: str
    value: str
    pos: int


def _tokenize_s_expr(text: str) -> List[_Token]:
    """Tokenize an S-expression string into paren, atom, and string tokens.

    Quoted strings (``"..."``) are returned as single STRING tokens whose
    value is the *unquoted* content (no surrounding quotes).  This correctly
    handles strings containing spaces, parens, colons, slashes, etc.
    """
    tokens: List[_Token] = []
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        if ch in " \t\r\n":
            i += 1
            continue

        if ch == "(":
            tokens.append(_Token(_TOK_LPAREN, "(", i))
            i += 1
            continue

        if ch == ")":
            tokens.append(_Token(_TOK_RPAREN, ")", i))
            i += 1
            continue

        if ch == ";":
            # Line comment — skip to end of line
            while i < n and text[i] != "\n":
                i += 1
            continue

        if ch == '"':
            # Quoted string — read until the closing quote (no escaped-quote
            # support needed for KiCad .net files, but handle "" as empty)
            start = i + 1
            i += 1
            buf: List[str] = []
            while i < n and text[i] != '"':
                buf.append(text[i])
                i += 1
            if i < n:
                i += 1  # consume closing "
            tokens.append(_Token(_TOK_STRING, "".join(buf), start))
            continue

        # Atom: read until whitespace or paren
        start = i
        while i < n and text[i] not in ' \t\r\n();"':
            i += 1
        value = text[start:i]
        tokens.append(_Token(_TOK_ATOM, value, start))

    return tokens


class _SExprParser:
    """A cursor-based recursive-descent parser over a token list.

    Provides lookahead, consume, and parenthesised-expression helpers that
    make the downstream KiCad-semantic parser straightforward.
    """

    def __init__(self, tokens: List[_Token]):
        self._tokens = tokens
        self._pos = 0

    @property
    def eof(self) -> bool:
        return self._pos >= len(self._tokens)

    def peek(self, offset: int = 0) -> Optional[_Token]:
        idx = self._pos + offset
        if idx >= len(self._tokens):
            return None
        return self._tokens[idx]

    def _cur(self) -> Optional[_Token]:
        return self.peek(0)

    def advance(self) -> _Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def expect(self, kind: str, expected_value: Optional[str] = None) -> _Token:
        tok = self._cur()
        if tok is None:
            raise ValueError(f"Unexpected end of input; expected {kind}")
        if tok.kind != kind:
            raise ValueError(
                f"Expected {kind} but got {tok.kind} ({tok.value!r} at pos {tok.pos})"
            )
        if expected_value is not None and tok.value != expected_value:
            raise ValueError(
                f"Expected {expected_value!r} but got {tok.value!r} at pos {tok.pos}"
            )
        return self.advance()

    def match(self, value: str, kind: str = _TOK_ATOM) -> bool:
        """Return True and advance if the current token matches *value*."""
        tok = self._cur()
        if tok is not None and tok.kind == kind and tok.value == value:
            self._pos += 1
            return True
        return False

    # -- list parsing ---------------------------------------------------------

    def parse_list(self) -> List[Union[_Token, list]]:
        """Parse a single S-expression form, returning a nested list."""
        tok = self._cur()
        if tok is None:
            raise ValueError("Unexpected end of input while parsing list")
        if tok.kind != _TOK_LPAREN:
            raise ValueError(f"Expected '(' but got {tok.kind} ({tok.value!r})")
        self._pos += 1  # consume '('

        items: List[Union[_Token, list]] = []
        while True:
            tok = self._cur()
            if tok is None:
                raise ValueError("Unexpected end of input; missing ')'")
            if tok.kind == _TOK_RPAREN:
                self._pos += 1  # consume ')'
                break
            if tok.kind == _TOK_LPAREN:
                items.append(self.parse_list())
            else:
                items.append(self.advance())

        return items


# ---------------------------------------------------------------------------
# KiCad-semantic parser
# ---------------------------------------------------------------------------


class NetlistParser:
    """Parse KiCad netlist files (S-expressions format) into structured data.

    Uses a recursive-descent tokenizer that correctly handles the S-expression
    format used by KiCad .net (netlist) files, including quoted strings with
    spaces, colons, and special characters.
    """

    def __init__(self):
        self.data: NetlistData = NetlistData()

    # -- public API -----------------------------------------------------------

    def parse_file(self, filepath: str | Path) -> NetlistData:
        """Parse a KiCad netlist file from disk.

        Args:
            filepath: Path to the .net file

        Returns:
            NetlistData containing parsed components and nets

        Raises:
            FileNotFoundError: If the file does not exist
            ValueError: If the file contains malformed S-expressions
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Netlist file not found: {filepath}")

        content = path.read_text(encoding="utf-8")
        return self.parse_content(content)

    def parse_content(self, content: str) -> NetlistData:
        """Parse netlist content from a string.

        Args:
            content: S-expression netlist content

        Returns:
            NetlistData containing parsed components and nets
        """
        self.data = NetlistData()

        # Tokenize and parse into nested S-expression lists
        tokens = _tokenize_s_expr(content)
        if not tokens:
            return self.data

        sexpr = _SExprParser(tokens)

        # Top-level form should be (kicad_netlist ...)
        top = sexpr.parse_list()

        # The first element of the top list is the symbol 'kicad_netlist'
        # followed by sub-lists (version, components, nets).
        self._dispatch_top_level(top)

        # Populate backward-compatible dict properties
        self._sync_compat_dicts()
        return self.data

    # -- top-level dispatch ---------------------------------------------------

    def _dispatch_top_level(self, items: List[Union[_Token, list]]) -> None:
        """Dispatch top-level sub-forms of ``(kicad_netlist ...)``."""
        idx = 0

        # First atom should be 'kicad_netlist'
        if idx < len(items) and isinstance(items[idx], _Token) and items[idx].value == "kicad_netlist":
            idx += 1
        else:
            # If the top-level doesn't start with kicad_netlist, still try to
            # parse version/components/nets wherever they appear.
            pass

        while idx < len(items):
            item = items[idx]
            if isinstance(item, _Token) and item.kind == _TOK_ATOM:
                symbol = item.value
                if symbol == "version":
                    # (version ...) may be inline
                    if idx + 1 < len(items) and isinstance(items[idx + 1], _Token):
                        self.data.version = items[idx + 1].value
                        idx += 2
                    else:
                        idx += 1
                elif symbol == "components":
                    if idx + 1 < len(items) and isinstance(items[idx + 1], list):
                        self._parse_components_list(items[idx + 1])
                        idx += 2
                    else:
                        idx += 1
                elif symbol == "nets":
                    if idx + 1 < len(items) and isinstance(items[idx + 1], list):
                        self._parse_nets_list(items[idx + 1])
                        idx += 2
                    else:
                        idx += 1
                else:
                    # Unknown top-level key — skip it
                    idx += 1
            elif isinstance(item, list):
                # A nested form without a preceding atom — try to parse it
                if len(item) > 0 and isinstance(item[0], _Token):
                    symbol = item[0].value
                    if symbol == "version" and len(item) > 1:
                        ver_tok = item[1]
                        if isinstance(ver_tok, _Token):
                            self.data.version = ver_tok.value
                    elif symbol == "components":
                        self._parse_components_list(item[1:])
                    elif symbol == "nets":
                        self._parse_nets_list(item[1:])
                idx += 1
            else:
                idx += 1

    # -- component parsing ----------------------------------------------------

    def _parse_components_list(self, items: List[Union[_Token, list]]) -> None:
        """Parse the contents of a ``(components ...)`` list."""
        for item in items:
            if not isinstance(item, list):
                continue
            self._parse_component_form(item)

    def _parse_component_form(self, items: List[Union[_Token, list]]) -> None:
        """Parse a single ``(comp ...)`` form."""
        if len(items) == 0 or not isinstance(items[0], _Token):
            return
        if items[0].value != "comp":
            return

        comp_ref: Optional[str] = None
        fields: Dict[str, str] = {}

        idx = 1
        while idx < len(items):
            item = items[idx]
            if isinstance(item, _Token) and item.kind == _TOK_ATOM:
                key = item.value
                # The next element might be a scalar value (e.g. (ref R1))
                # or a list (e.g. (field ...) / (value ...))
                if idx + 1 < len(items):
                    val = items[idx + 1]
                    if isinstance(val, _Token):
                        # Simple (key value) form, e.g. (ref R1)
                        if key == "ref":
                            comp_ref = val.value
                        else:
                            fields[key] = val.value
                        idx += 2
                        continue
                    elif isinstance(val, list):
                        # Complex form
                        if key == "field":
                            self._parse_field_form(val, fields)
                            idx += 2
                            continue
                        elif key in ("value", "footprint"):
                            # (value "10k") or (value "10k" (footprint "..."))
                            self._parse_value_footprint(key, val, fields)
                            idx += 2
                            continue
                        else:
                            idx += 2
                            continue
                idx += 1
            elif isinstance(item, list):
                # (ref R1) or (value ...) or (field ...) as a sub-expression
                if len(item) > 0 and isinstance(item[0], _Token):
                    sub_key = item[0].value
                    if sub_key == "ref":
                        if len(item) > 1 and isinstance(item[1], _Token):
                            comp_ref = item[1].value
                    elif sub_key == "field":
                        self._parse_field_form(item[1:], fields)
                    elif sub_key in ("value", "footprint"):
                        self._parse_value_footprint(sub_key, item[1:], fields)
                idx += 1
            else:
                idx += 1

        if comp_ref:
            comp = Component(ref=comp_ref, fields=fields)
            self.data.components_list.append(comp)
            self.data.components[comp_ref] = dict(fields)

    def _parse_field_form(
        self, items: List[Union[_Token, list]], fields: Dict[str, str]
    ) -> None:
        """Parse a ``field`` form.

        Handles several KiCad field sub-formats:

        * ``(field Name "value")`` or ``(field Name value)``
        * ``(field (name Name) (text "value"))``
        * ``(field Name (value "text") (type ...) ...)``  (multi-token forms)
        """
        # Collect all string/atom tokens; the first is the field name.
        name: Optional[str] = None
        value: Optional[str] = None

        for item in items:
            if isinstance(item, _Token):
                if name is None:
                    name = item.value
                elif value is None:
                    value = item.value
            elif isinstance(item, list):
                # (name X) or (text Y) sub-forms, or (value Z)
                if len(item) >= 2 and isinstance(item[0], _Token):
                    sub_key = item[0].value
                    if sub_key in ("name", "text", "value"):
                        # The value could be a single token or another list
                        rest = item[1:]
                        v = self._extract_text_value(rest)
                        if sub_key == "name":
                            name = v
                        else:
                            value = v

        if name is not None:
            fields[name] = value or ""

    def _parse_value_footprint(
        self, key: str, items: List[Union[_Token, list]], fields: Dict[str, str]
    ) -> None:
        """Parse a ``(value ...)`` or ``(footprint ...)`` form.

        ``(value "10k")`` → fields["Value"] = "10k"
        ``(value "10k" (footprint "R_0805"))`` → both fields set
        """
        # First token is the value
        val: Optional[str] = None
        for item in items:
            if isinstance(item, _Token):
                val = item.value
                break

        if val is not None:
            fields[key.capitalize()] = val

        # Look for nested (footprint ...) or (value ...) sub-forms
        for item in items:
            if isinstance(item, list) and len(item) >= 2 and isinstance(item[0], _Token):
                sub_key = item[0].value
                if sub_key in ("footprint", "value", "name"):
                    sub_val = self._extract_text_value(item[1:])
                    if sub_val is not None:
                        fields[sub_key.capitalize()] = sub_val

    @staticmethod
    def _extract_text_value(items: List[Union[_Token, list]]) -> Optional[str]:
        """Extract a text value from a list of tokens/lists."""
        for item in items:
            if isinstance(item, _Token):
                return item.value
            if isinstance(item, list):
                # A nested list might contain the actual string token
                for sub in item:
                    if isinstance(sub, _Token):
                        return sub.value
        return None

    # -- net parsing ----------------------------------------------------------

    def _parse_nets_list(self, items: List[Union[_Token, list]]) -> None:
        """Parse the contents of a ``(nets ...)`` list."""
        for item in items:
            if not isinstance(item, list):
                continue
            net = self._parse_net_form(item)
            if net is not None:
                self.data.nets_list.append(net)

    def _parse_net_form(
        self, items: List[Union[_Token, list]]
    ) -> Optional[Net]:
        """Parse a single ``(net ...)`` form."""
        if len(items) == 0 or not isinstance(items[0], _Token):
            return None
        if items[0].value != "net":
            return None

        net = Net()
        idx = 1
        while idx < len(items):
            item = items[idx]
            if isinstance(item, _Token) and item.kind == _TOK_ATOM:
                key = item.value
                if key == "code":
                    # (code 1)
                    if idx + 1 < len(items) and isinstance(items[idx + 1], _Token):
                        try:
                            net.code = int(items[idx + 1].value)
                        except ValueError:
                            net.code = 0
                        idx += 2
                        continue
                elif key == "name":
                    if idx + 1 < len(items) and isinstance(items[idx + 1], _Token):
                        net.name = items[idx + 1].value
                        idx += 2
                        continue
                idx += 1
            elif isinstance(item, list):
                if len(item) > 0 and isinstance(item[0], _Token):
                    sub_key = item[0].value
                    if sub_key == "code" and len(item) > 1:
                        try:
                            net.code = int(item[1].value)
                        except (ValueError, AttributeError):
                            net.code = 0
                    elif sub_key == "name" and len(item) > 1:
                        name_val = item[1]
                        if isinstance(name_val, _Token):
                            net.name = name_val.value
                    elif sub_key == "node":
                        node = self._parse_node_form(item[1:])
                        if node:
                            net.nodes.append(node)
                idx += 1
            else:
                idx += 1

        return net if net.name or net.nodes else (net if net.code != 0 else None)

    def _parse_node_form(
        self, items: List[Union[_Token, list]]
    ) -> Optional[Node]:
        """Parse a ``(node ...)`` form.

        Handles both orderings:
        * ``(node (ref R1) (pin 1))``
        * ``(node (pin 1) (ref R1))``  (defensive)
        """
        ref: Optional[str] = None
        pin: Optional[str] = None

        for item in items:
            if isinstance(item, list) and len(item) >= 2 and isinstance(item[0], _Token):
                sub_key = item[0].value
                sub_val = item[1]
                if isinstance(sub_val, _Token):
                    if sub_key == "ref":
                        ref = sub_val.value
                    elif sub_key == "pin":
                        pin = sub_val.value
            elif isinstance(item, _Token):
                # Bare (node ref pin) — rare but handle it
                if ref is None:
                    ref = item.value
                elif pin is None:
                    pin = item.value

        if ref is not None and pin is not None:
            return Node(ref=ref, pin=pin)
        return None

    # -- backward-compat sync -------------------------------------------------

    def _sync_compat_dicts(self) -> None:
        """Populate backward-compatible `components` and `nets` dicts."""
        # components dict already populated during parsing, but rebuild to
        # ensure consistency
        components: Dict[str, Dict] = {}
        for comp in self.data.components_list:
            components[comp.ref] = dict(comp.fields)
        self.data.components = components

        nets: Dict[str, List[str]] = {}
        for net in self.data.nets_list:
            net_id = net.name if net.name else f"#{net.code}"
            nets[net_id] = net.node_ids()
        self.data.nets = nets


# ---------------------------------------------------------------------------
# Design-rule checker
# ---------------------------------------------------------------------------


class DesignRuleChecker:
    """Basic DRC rules for netlist validation.

    Runs design rule checks on parsed netlist data to identify common
    issues like floating nets and components with unusual connection counts.
    """

    def __init__(self, min_trace_width: float = 0.25, min_clearance: float = 0.25):
        """Initialize the DRC checker.

        Args:
            min_trace_width: Minimum trace width in mm
            min_clearance: Minimum clearance in mm
        """
        self.min_trace_width = min_trace_width
        self.min_clearance = min_clearance
        self.rules = [
            self._check_net_isolation,
            self._check_component_pad_count,
            self._check_node_references,
        ]

    def check_netlist(self, netlist_data: NetlistData) -> List[ValidationResult]:
        """Run all DRC rules on the netlist data.

        Args:
            netlist_data: Parsed netlist data to validate

        Returns:
            List of validation results, one per violation found
        """
        violations: List[ValidationResult] = []
        for rule in self.rules:
            violations.extend(rule(netlist_data))
        return violations

    def _check_net_isolation(
        self, netlist_data: NetlistData
    ) -> List[ValidationResult]:
        """Check for nets with fewer than 2 nodes (floating or unconnected nets)."""
        violations: List[ValidationResult] = []
        for net in netlist_data.nets_list:
            if len(net.nodes) < 2:
                violations.append(
                    ValidationResult(
                        rule_id="NET_ISOLATION",
                        description=f"Net '{net.name or f'#{net.code}'}' has only "
                        f"{len(net.nodes)} node(s) — may be floating",
                        severity="warning",
                        net=net.name or f"#{net.code}",
                        details=f"Nodes: {net.node_ids()}",
                    )
                )
        return violations

    def _check_component_pad_count(
        self, netlist_data: NetlistData
    ) -> List[ValidationResult]:
        """Check that components have reasonable number of connections.

        Warns about components with unusually high (>50) connection counts.
        """
        violations: List[ValidationResult] = []
        connections: Dict[str, int] = {}
        for net in netlist_data.nets_list:
            for node in net.nodes:
                connections[node.ref] = connections.get(node.ref, 0) + 1

        for comp_ref, count in connections.items():
            if comp_ref in netlist_data.components:
                if count > 50:
                    violations.append(
                        ValidationResult(
                            rule_id="COMP_PAD_COUNT",
                            description=f"Component '{comp_ref}' has {count} "
                            "connections — unusually high",
                            severity="info",
                            component=comp_ref,
                            details=f"Connected to {count} pins across nets",
                        )
                    )
        return violations

    def _check_node_references(
        self, netlist_data: NetlistData
    ) -> List[ValidationResult]:
        """Check that all net nodes reference known components."""
        violations: List[ValidationResult] = []
        known_refs = set(netlist_data.components.keys())

        for net in netlist_data.nets_list:
            for node in net.nodes:
                if node.ref not in known_refs:
                    violations.append(
                        ValidationResult(
                            rule_id="UNDEFINED_COMPONENT",
                            description=f"Net '{net.name}' references unknown "
                            f"component '{node.ref}'",
                            severity="error",
                            net=net.name,
                            component=node.ref,
                            details=f"Node {node} on net '{net.name}' references "
                            "a component not declared in the components section",
                        )
                    )
        return violations


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------


def parse_netlist(filepath: str | Path) -> NetlistData:
    """Convenience function to parse a netlist file.

    Args:
        filepath: Path to the KiCad .net file

    Returns:
        NetlistData containing parsed components and nets
    """
    parser = NetlistParser()
    return parser.parse_file(filepath)


def validate_netlist(
    netlist_data: NetlistData,
    min_trace_width: float = 0.25,
    min_clearance: float = 0.25,
) -> List[ValidationResult]:
    """Convenience function to validate netlist data.

    Args:
        netlist_data: Parsed netlist data to validate
        min_trace_width: Minimum trace width in mm
        min_clearance: Minimum clearance in mm

    Returns:
        List of validation results (violations found)
    """
    drc = DesignRuleChecker(min_trace_width, min_clearance)
    return drc.check_netlist(netlist_data)
