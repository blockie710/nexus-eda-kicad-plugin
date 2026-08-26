# SPDX-License-Identifier: Apache-2.0
"""KiCad netlist parser for extracting structured data from S-expression format.

This module provides:
    - NetlistParser: Parse KiCad .net files into structured data
    - DesignRuleChecker: Basic DRC validation rules
    - NetlistData: Dataclass holding parsed netlist contents
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class NetlistData:
    """Structured representation of a parsed KiCad netlist.
    
    Attributes:
        version: Netlist format version string
        components: Dict of component reference designators to their field data
        nets: Dict of net names to lists of node identifiers (e.g. "R1/1")
    """
    version: str = ""
    components: Dict[str, Dict] = field(default_factory=dict)
    nets: Dict[str, List[str]] = field(default_factory=dict)


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
    severity: str
    component: Optional[str] = None
    net: Optional[str] = None
    details: Optional[str] = None


class NetlistParser:
    """Parse KiCad netlist files (S-expression format) into structured data.
    
    Uses a recursive-descent parenthesis-matching approach to correctly
    handle nested S-expressions.
    """
    
    def __init__(self):
        self.data = NetlistData()
    
    def parse_file(self, filepath: str | Path) -> NetlistData:
        """Parse a KiCad netlist file from disk.
        
        Args:
            filepath: Path to the .net file
            
        Returns:
            NetlistData containing parsed components and nets
            
        Raises:
            FileNotFoundError: If the file does not exist
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Netlist file not found: {filepath}")
        
        content = path.read_text(encoding='utf-8')
        return self.parse_content(content)
    
    def parse_content(self, content: str) -> NetlistData:
        """Parse netlist content from a string.
        
        Args:
            content: S-expression netlist content
            
        Returns:
            NetlistData containing parsed components and nets
        """
        self.data = NetlistData()
        
        # Remove comments
        content = re.sub(r'#.*', '', content)
        
        # Extract version
        version_match = re.search(r'\(version\s+([^\)]+)\)', content)
        if version_match:
            self.data.version = version_match.group(1).strip()
        
        # Parse components - find all (comp ... ) blocks
        self._parse_components(content)
        
        # Parse nets - find all (net ... ) blocks (but not (nets ...))
        self._parse_nets(content)
        
        return self.data
    
    def _find_matching_paren(self, content: str, open_pos: int) -> int:
        """Find the position of the closing parenthesis matching the opening one.
        
        Args:
            content: The full S-expression content
            open_pos: Position of the opening '(' 
            
        Returns:
            Position of the matching closing ')', or -1 if not found
        """
        paren_count = 0
        for i in range(open_pos, len(content)):
            if content[i] == '(':
                paren_count += 1
            elif content[i] == ')':
                paren_count -= 1
                if paren_count == 0:
                    return i
        return -1
    
    def _parse_components(self, content: str) -> None:
        """Parse components section by finding all (comp ... ) blocks."""
        pos = 0
        while True:
            comp_start = content.find('(comp', pos)
            if comp_start == -1:
                break
            
            comp_end = self._find_matching_paren(content, comp_start)
            if comp_end != -1:
                comp_content = content[comp_start:comp_end+1]
                self._parse_single_component(comp_content)
                pos = comp_end + 1
            else:
                break
    
    def _parse_single_component(self, content: str) -> None:
        """Parse a single (comp ...) block.
        
        Args:
            content: The (comp ...) S-expression string
        """
        comp_ref = None
        comp_fields = {}
        
        # Extract ref - matches (ref R1)
        ref_match = re.search(r'\(ref\s+([^)]+)\)', content)
        if ref_match:
            comp_ref = ref_match.group(1).strip()
        
        # Extract fields - match (field Name "value") or (field Name value)
        field_pattern = r'\(field\s+(\w+)\s+(.+?)\)'
        field_matches = re.findall(field_pattern, content, re.DOTALL)
        for field_name, field_value in field_matches:
            # Clean up value - strip whitespace and quotes
            field_value = field_value.strip().strip('"')
            comp_fields[field_name.strip()] = field_value
        
        if comp_ref:
            self.data.components[comp_ref] = comp_fields
    
    def _parse_nets(self, content: str) -> None:
        """Parse nets section by finding all (net ... ) blocks.
        
        Searches for '(net ' (with a space), which matches (net but NOT
        (nets since 'nets' is not followed by a space after 'net'.
        """
        pos = 0
        while True:
            net_start = content.find('(net ', pos)
            if net_start == -1:
                break
            
            net_end = self._find_matching_paren(content, net_start)
            if net_end != -1:
                net_content = content[net_start:net_end+1]
                self._parse_single_net(net_content)
                pos = net_end + 1
            else:
                break
    
    def _parse_single_net(self, content: str) -> None:
        """Parse a single (net ...) block.
        
        Args:
            content: The (net ...) S-expression string
        """
        net_name = None
        nodes = []
        
        # Extract name - match (name "NetName") or (name NetName)
        name_match = re.search(r'\(name\s+"?([^")]+)?"\)', content)
        if name_match:
            net_name = name_match.group(1).strip()
        
        # Extract nodes - match (node (ref R1) (pin 1))
        # The pattern handles: (node (ref R1) (pin 1)) and (node (ref U1) (pin AVCC))
        # Note: ref and pin values can be alphanumeric (including uppercase letters)
        node_pattern = r'\(node\s+\(ref\s+([^)]+)\)\s+\(pin\s+([^)]+)\)\)'
        node_matches = re.findall(node_pattern, content)
        for ref, pin in node_matches:
            nodes.append(f"{ref.strip()}/{pin.strip()}")
        
        if net_name and nodes:
            self.data.nets[net_name] = nodes


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
        ]
    
    def check_netlist(self, netlist_data: NetlistData) -> List[ValidationResult]:
        """Run all DRC rules on the netlist data.
        
        Args:
            netlist_data: Parsed netlist data to validate
            
        Returns:
            List of validation results, one per violation found
        """
        violations = []
        for rule in self.rules:
            violations.extend(rule(netlist_data))
        return violations
    
    def _check_net_isolation(self, netlist_data: NetlistData) -> List[ValidationResult]:
        """Check for nets with fewer than 2 nodes (floating or unconnected nets)."""
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
    
    def _check_component_pad_count(self, netlist_data: NetlistData) -> List[ValidationResult]:
        """Check that components have reasonable number of connections.
        
        Warns about components with unusually high (>50) connection counts.
        """
        violations = []
        connections = {}
        for net_name, nodes in netlist_data.nets.items():
            for node in nodes:
                if '/' in node:
                    comp_ref, pin = node.split('/', 1)
                    connections[comp_ref] = connections.get(comp_ref, 0) + 1
        
        for comp_ref, count in connections.items():
            if comp_ref in netlist_data.components:
                if count > 50:
                    violations.append(ValidationResult(
                        rule_id="COMP_PAD_COUNT",
                        description=f"Component '{comp_ref}' has {count} connections - unusually high",
                        severity="info",
                        component=comp_ref,
                        details=f"Connected to {count} pins across nets"
                    ))
        return violations


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
    min_clearance: float = 0.25
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