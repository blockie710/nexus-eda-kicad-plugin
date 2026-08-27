# SPDX-License-Identifier: Apache-2.0
"""Debug version of netlist parser."""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class NetlistData:
    """Structured representation of a parsed KiCad netlist."""
    version: str = ""
    components: dict[str, dict] = field(default_factory=dict)
    nets: dict[str, list[str]] = field(default_factory=dict)
    # nets[net_name] = [node1, node2, ...] where node is "comp_ref/pin_num"


class NetlistParser:
    """Parse KiCad netlist files (S-expression format) into structured data."""

    def __init__(self):
        self.data = NetlistData()

    def parse_file(self, filepath: str | Path) -> NetlistData:
        """Parse a KiCad netlist file."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Netlist file not found: {filepath}")

        content = path.read_text(encoding='utf-8')
        print(f"[DEBUG] Raw content length: {len(content)}")
        print(f"[DEBUG] First 200 chars: {content[:200]!r}")
        return self.parse_content(content)

    def parse_content(self, content: str) -> NetlistData:
        """Parse netlist content from string."""
        print(f"[DEBUG] Parsing content: {content[:100]!r}")
        self.data = NetlistData()

        # Remove comments and normalize whitespace
        content = re.sub(r'#.*', '', content)
        content = re.sub(r'\s+', ' ', content).strip()
        print(f"[DEBUG] After cleanup: {content[:100]!r}")

        # Parse top-level expressions
        tokens = self._tokenize(content)
        print(f"[DEBUG] Tokens: {tokens[:20]}...")
        if not tokens:
            return self.data

        # Expect (kicad_netlist (version ...) (components ...) (nets ...))
        i = 0
        while i < len(tokens):
            if tokens[i] == '(':
                i += 1
                if i < len(tokens) and tokens[i] == 'kicad_netlist':
                    print(f"[DEBUG] Found kicad_netlist at token {i-1}")
                    i = self._parse_kicad_netlist(tokens, i)
                else:
                    print(f"[DEBUG] Skipping unknown token: "
                          f"{tokens[i-1] if i>0 else 'START'}")
                    i = self._skip_paren(tokens, i)
            else:
                print(f"[DEBUG] Skipping non-paren token: {tokens[i]}")
                i += 1

        print(f"[DEBUG] Final data: version='{self.data.version}', "
              f"components={list(self.data.components.keys())}, "
              f"nets={list(self.data.nets.keys())}")
        return self.data

    def _tokenize(self, s: str) -> list[str]:
        """Simple tokenizer for S-expressions."""
        tokens = []
        i = 0
        while i < len(s):
            if s[i] in '()':
                tokens.append(s[i])
                i += 1
            elif s[i].isspace():
                i += 1
            else:
                # Collect atom
                start = i
                while i < len(s) and not s[i].isspace() and s[i] not in '()':
                    i += 1
                tokens.append(s[start:i])
        return tokens

    def _skip_paren(self, tokens: list[str], i: int) -> int:
        """Skip a parenthesized expression."""
        depth = 0
        start_i = i
        while i < len(tokens):
            if tokens[i] == '(':
                depth += 1
            elif tokens[i] == ')':
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        print(f"[DEBUG] _skip_paren from {start_i} to {i} (unclosed)")
        return i

    def _parse_kicad_netlist(self, tokens: list[str], i: int) -> int:
        """Parse (kicad_netlist ...) expression."""
        print(f"[DEBUG] _parse_kicad_netlist starting at token {i}: {tokens[i:i+10]}")
        depth = 1
        i += 1
        current = []

        while i < len(tokens) and depth > 0:
            if tokens[i] == '(':
                depth += 1
                current.append(tokens[i])
            elif tokens[i] == ')':
                depth -= 1
                if depth == 0:
                    break
                current.append(tokens[i])
            else:
                current.append(tokens[i])
            i += 1

        print(f"[DEBUG] _parse_kicad_netlist content tokens: {' '.join(current[:50])}")
        # Parse the content
        content_tokens = self._tokenize(' '.join(current))
        print(f"[DEBUG] Content tokens: {content_tokens[:20]}...")
        j = 0
        while j < len(content_tokens):
            if content_tokens[j] == '(':
                j += 1
                if j < len(content_tokens):
                    if content_tokens[j] == 'version':
                        print(f"[DEBUG] Found version at token {j}")
                        j = self._parse_version(content_tokens, j)
                    elif content_tokens[j] == 'components':
                        print(f"[DEBUG] Found components at token {j}")
                        j = self._parse_components(content_tokens, j)
                    elif content_tokens[j] == 'nets':
                        print(f"[DEBUG] Found nets at token {j}")
                        j = self._parse_nets(content_tokens, j)
                    else:
                        print(f"[DEBUG] Skipping unknown section: {content_tokens[j]}")
                        j = self._skip_paren(content_tokens, j)
                else:
                    j += 1
            else:
                print(f"[DEBUG] Skipping token in content: {content_tokens[j]}")
                j += 1

        return i

    def _parse_version(self, tokens: list[str], i: int) -> int:
        """Parse (version ...) expression."""
        print(f"[DEBUG] _parse_version at token {i}: {tokens[i:i+5]}")
        if i >= len(tokens) or tokens[i] != '(':
            return i
        i += 1  # skip '('
        if i < len(tokens) and tokens[i] == 'version':
            i += 1
            if i < len(tokens):
                self.data.version = tokens[i]
                print(f"[DEBUG] Set version to: {self.data.version}")
                i += 1
        # skip to closing ')'
        while i < len(tokens) and tokens[i] != ')':
            i += 1
        if i < len(tokens) and tokens[i] == ')':
            i += 1
        return i

    def _parse_components(self, tokens: list[str], i: int) -> int:
        """Parse (components ...) expression."""
        print(f"[DEBUG] _parse_components at token {i}: {tokens[i:i+5]}")
        if i >= len(tokens) or tokens[i] != '(':
            return i
        i += 1  # skip '('

        while i < len(tokens) and tokens[i] != ')':
            if tokens[i] == '(':
                i += 1
                if i < len(tokens) and tokens[i] == 'comp':
                    print(f"[DEBUG] Found comp at token {i-1}")
                    i = self._parse_component(tokens, i)
                else:
                    print(f"[DEBUG] Skipping unknown in components: {tokens[i-1]}")
                    i = self._skip_paren(tokens, i)
            else:
                i += 1

        if i < len(tokens) and tokens[i] == ')':
            i += 1
        return i

    def _parse_component(self, tokens: list[str], i: int) -> int:
        """Parse (comp ...) expression."""
        print(f"[DEBUG] _parse_component at token {i}: {tokens[i:i+10]}")
        if i >= len(tokens) or tokens[i] != '(':
            return i
        i += 1  # skip '('

        comp_ref = None
        comp_fields = {}

        while i < len(tokens) and tokens[i] != ')':
            if tokens[i] == '(':
                i += 1
                if i < len(tokens) and tokens[i] == 'ref':
                    print(f"[DEBUG] Found ref at token {i-1}")
                    i += 1
                    if i < len(tokens):
                        comp_ref = tokens[i]
                        print(f"[DEBUG] Component ref: {comp_ref}")
                        i += 1
                elif tokens[i] == 'field':
                    print(f"[DEBUG] Found field at token {i-1}")
                    i += 1
                    if i < len(tokens) and tokens[i] == '(':
                        i += 1
                        if i < len(tokens):
                            field_name = tokens[i]
                            print(f"[DEBUG] Field name: {field_name}")
                            i += 1
                            if i < len(tokens) and tokens[i] == '(':
                                i += 1
                                if i < len(tokens):
                                    field_value = tokens[i]
                                    print(f"[DEBUG] Field value: {field_value}")
                                    i += 1
                                # skip to closing ')'
                                while i < len(tokens) and tokens[i] != ')':
                                    i += 1
                                if i < len(tokens) and tokens[i] == ')':
                                    i += 1
                            comp_fields[field_name] = field_value
                        # skip to closing ')'
                        while i < len(tokens) and tokens[i] != ')':
                            i += 1
                        if i < len(tokens) and tokens[i] == ')':
                            i += 1
                else:
                    print(f"[DEBUG] Skipping unknown in comp: {tokens[i-1]}")
                    i = self._skip_paren(tokens, i)
            else:
                i += 1

        if comp_ref:
            self.data.components[comp_ref] = comp_fields
            print(f"[DEBUG] Added component {comp_ref} with fields: {list(comp_fields.keys())}")

        # skip to closing ')'
        while i < len(tokens) and tokens[i] != ')':
            i += 1
        if i < len(tokens) and tokens[i] == ')':
            i += 1
        return i

    def _parse_nets(self, tokens: list[str], i: int) -> int:
        """Parse (nets ...) expression."""
        print(f"[DEBUG] _parse_nets at token {i}: {tokens[i:i+5]}")
        if i >= len(tokens) or tokens[i] != '(':
            return i
        i += 1  # skip '('

        while i < len(tokens) and tokens[i] != ')':
            if tokens[i] == '(':
                i += 1
                if i < len(tokens) and tokens[i] == 'net':
                    print(f"[DEBUG] Found net at token {i-1}")
                    i = self._parse_net(tokens, i)
                else:
                    print(f"[DEBUG] Skipping unknown in nets: {tokens[i-1]}")
                    i = self._skip_paren(tokens, i)
            else:
                i += 1

        if i < len(tokens) and tokens[i] == ')':
            i += 1
        return i

    def _parse_net(self, tokens: list[str], i: int) -> int:
        """Parse (net ...) expression."""
        print(f"[DEBUG] _parse_net at token {i}: {tokens[i:i+10]}")
        if i >= len(tokens) or tokens[i] != '(':
            return i
        i += 1  # skip '('

        net_name = None
        nodes = []

        while i < len(tokens) and tokens[i] != ')':
            if tokens[i] == '(':
                i += 1
                if i < len(tokens) and tokens[i] == 'name':
                    print(f"[DEBUG] Found name at token {i-1}")
                    i += 1
                    if i < len(tokens):
                        net_name = tokens[i]
                        print(f"[DEBUG] Net name: {net_name}")
                        i += 1
                elif tokens[i] == 'node':
                    print(f"[DEBUG] Found node at token {i-1}")
                    i += 1
                    if i < len(tokens) and tokens[i] == '(':
                        i += 1
                        if i < len(tokens):
                            node_ref = tokens[i]
                            print(f"[DEBUG] Node ref: {node_ref}")
                            i += 1
                            if i < len(tokens) and tokens[i] == ')':
                                i += 1
                            nodes.append(node_ref)
                        # skip to closing ')'
                        while i < len(tokens) and tokens[i] != ')':
                            i += 1
                        if i < len(tokens) and tokens[i] == ')':
                            i += 1
                else:
                    print(f"[DEBUG] Skipping unknown in net: {tokens[i-1]}")
                    i = self._skip_paren(tokens, i)
            else:
                i += 1

        if net_name and nodes:
            self.data.nets[net_name] = nodes
            print(f"[DEBUG] Added net {net_name} with nodes: {nodes}")

        # skip to closing ')'
        while i < len(tokens) and tokens[i] != ')':
            i += 1
        if i < len(tokens) and tokens[i] == ')':
            i += 1
        return i


@dataclass
class ValidationResult:
    """Result of a DRC check."""
    rule_id: str
    description: str
    severity: str  # 'error', 'warning', 'info'
    component: str | None = None
    net: str | None = None
    details: str | None = None


class DesignRuleChecker:
    """Basic DRC rules for netlist validation."""

    def __init__(self, min_trace_width: float = 0.25, min_clearance: float = 0.25):
        self.min_trace_width = min_trace_width  # mm
        self.min_clearance = min_clearance      # mm
        self.rules = [
            self._check_net_isolation,
            self._check_component_pad_count,
        ]

    def check_netlist(self, netlist_data: NetlistData) -> list[ValidationResult]:
        """Run all DRC rules on the netlist data."""
        violations = []
        for rule in self.rules:
            violations.extend(rule(netlist_data))
        return violations

    def _check_net_isolation(self, netlist_data: NetlistData) -> list[ValidationResult]:
        """Check for nets with only one node (floating nets)."""
        violations = []
        for net_name, nodes in netlist_data.nets.items():
            if len(nodes) < 2:
                violations.append(ValidationResult(
                    rule_id="NET_ISOLATION",
                    description=f"Net '{net_name}' has only {len(nodes)} node(s) - may be floating",
                    severity="warning",
                    net=net_name,
                    details=f"Nodes: {nodes}"
                ))
        return violations

    def _check_component_pad_count(self, netlist_data: NetlistData) -> list[ValidationResult]:
        """Check that components have reasonable number of connections."""
        violations = []
        # Count connections per component from nets
        connections = {}
        for nodes in netlist_data.nets.values():
            for node in nodes:
                if '/' in node:
                    comp_ref, _pin = node.split('/', 1)
                    connections[comp_ref] = connections.get(comp_ref, 0) + 1

        for comp_ref, count in connections.items():
            # Simple heuristic: warn if > 50 connections (unlikely for most components)
            if comp_ref in netlist_data.components and count > 50:
                    violations.append(ValidationResult(
                        rule_id="COMP_PAD_COUNT",
                        description=f"Component '{comp_ref}' has {count} connections - unusually high",
                        severity="info",
                        component=comp_ref,
                        details=f"Connected to {count} pins across nets"
                    ))
        return violations


def parse_netlist(filepath: str | Path) -> NetlistData:
    """Convenience function to parse a netlist file."""
    parser = NetlistParser()
    return parser.parse_file(filepath)


def validate_netlist(netlist_data: NetlistData,
                    min_trace_width: float = 0.25,
                    min_clearance: float = 0.25) -> list[ValidationResult]:
    """Convenience function to validate netlist data."""
    drc = DesignRuleChecker(min_trace_width, min_clearance)
    return drc.check_netlist(netlist_data)
