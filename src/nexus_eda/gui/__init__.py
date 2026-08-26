# SPDX-License-Identifier: Apache-2.0
"""GUI components for the Nexus-EDA KiCad plugin.

This module provides rendering for the dual-stack architecture:
- Native ImGui (C++) production UI — lives in src/nexus_eda/gui/
- React/JSX HTML preview — lives in preview/src/

The Python GUI module is used for headless rendering tests, the HTML
preview, and as a reference for the C++ ImGui implementation.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from nexus_eda.netlist import NetlistData, ValidationResult

__all__ = [
    "NetlistViewer",
    "ViewerConfig",
    "render_netlist_html",
    "render_validation_results_html",
    "COLORS",
]


# Color scheme matching the Nexus-EDA design system
COLORS = {
    "background": "#0f0f1a",
    "panel": "#1a1a2e",
    "panel_border": "#2a2a4e",
    "text_primary": "#e0e0e0",
    "text_secondary": "#a0a0a0",
    "accent": "#00d4ff",
    "accent_secondary": "#7c3aed",
    "success": "#10b981",
    "warning": "#f59e0b",
    "error": "#ef4444",
    "info": "#3b82f6",
    "net_wire": "#4b5563",
    "net_selected": "#00d4ff",
}


@dataclass
class ViewerConfig:
    """Configuration for the netlist viewer."""
    show_components: bool = True
    show_nets: bool = True
    show_validation: bool = True
    highlight_unrouted: bool = True
    max_nets_display: int = 100
    selected_net: Optional[str] = None


class NetlistViewer:
    """Headless netlist viewer that can render to HTML or text.
    
    This class mirrors the ImGui netlist viewer that will be implemented
    in C++ for the native KiCad plugin. The Python version is used for:
    - Headless testing and verification
    - HTML preview generation
    - Reference implementation
    """
    
    def __init__(self, config: Optional[ViewerConfig] = None):
        self.config = config or ViewerConfig()
    
    def render_text(
        self,
        netlist: NetlistData,
        violations: Optional[List[ValidationResult]] = None
    ) -> str:
        """Render the netlist as formatted ASCII text."""
        lines = []
        lines.append("=" * 60)
        lines.append("  NEXUS-EDA NETLIST VIEWER")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"  Version: {netlist.version or '(not specified)'}")
        lines.append(f"  Components: {len(netlist.components)}")
        lines.append(f"  Nets: {len(netlist.nets)}")
        lines.append("")
        
        if self.config.show_components and netlist.components:
            lines.append("-" * 60)
            lines.append("  COMPONENTS")
            lines.append("-" * 60)
            for ref, fields in sorted(netlist.components.items()):
                value = fields.get('Value', '?')
                footprint = fields.get('Footprint', 'N/A')
                lines.append(f"    {ref:6s} | {value:20s} | {footprint}")
            lines.append("")
        
        if self.config.show_nets and netlist.nets:
            lines.append("-" * 60)
            lines.append("  NETS")
            lines.append("-" * 60)
            
            display_nets = list(netlist.nets.items())[:self.config.max_nets_display]
            for net_name, nodes in display_nets:
                prefix = "[*]" if self.config.selected_net == net_name else "   "
                lines.append(f"  {prefix} {net_name} ({len(nodes)} nodes)")
                for node in nodes:
                    lines.append(f"       -> {node}")
            
            if len(netlist.nets) > self.config.max_nets_display:
                remaining = len(netlist.nets) - self.config.max_nets_display
                lines.append(f"       ... and {remaining} more nets")
            lines.append("")
        
        if self.config.show_validation and violations:
            lines.append("-" * 60)
            lines.append("  VALIDATION RESULTS")
            lines.append("-" * 60)
            for v in violations:
                marker = {"error": "[!]", "warning": "[?]", "info": "[i]"}.get(v.severity, "[?]")
                target = v.component or v.net or ""
                lines.append(f"  {marker} [{v.severity:7s}] {v.rule_id}: {v.description}")
                if target:
                    lines.append(f"       Target: {target}")
                lines.append("")
        
        lines.append("=" * 60)
        return "\n".join(lines)
    
    def render_html(
        self,
        netlist: NetlistData,
        violations: Optional[List[ValidationResult]] = None
    ) -> str:
        """Render the netlist as styled HTML."""
        return render_netlist_html(netlist, violations, self.config)


def render_netlist_html(
    netlist: NetlistData,
    violations: Optional[List[ValidationResult]] = None,
    config: Optional[ViewerConfig] = None
) -> str:
    """Render netlist data as HTML with Nexus-EDA styling."""
    config = config or ViewerConfig()
    
    # Build CSS variables
    css_vars = "\n".join(
        f"            --{k}: {v};" for k, v in COLORS.items()
    )
    
    parts = []
    parts.append("""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Nexus-EDA Netlist Viewer</title>
    <style>
        :root {
""")
    parts.append(css_vars)
    parts.append("""
        }
        body {
            margin: 0; padding: 20px;
            background: var(--bg); color: var(--text-primary);
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            font-size: 14px; line-height: 1.6;
        }
        .header {
            background: var(--panel); border: 1px solid var(--panel-border);
            border-radius: 8px; padding: 16px 24px; margin-bottom: 20px;
        }
        .header h1 { margin: 0 0 8px 0; font-size: 18px; font-weight: 600; color: var(--accent); }
        .header-stats { display: flex; gap: 24px; color: var(--text-secondary); font-size: 13px; }
        .stat { display: flex; gap: 4px; }
        .stat-value { color: var(--accent); font-weight: 600; }
        .section {
            background: var(--panel); border: 1px solid var(--panel-border);
            border-radius: 8px; padding: 16px; margin-bottom: 16px;
        }
        .section-title {
            font-size: 14px; font-weight: 600; color: var(--accent);
            margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--panel-border);
        }
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 6px 12px; border-bottom: 1px solid var(--panel-border); }
        th { color: var(--text-secondary); font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
        tr:hover { background: rgba(0, 212, 255, 0.05); }
        .net-list { list-style: none; padding: 0; margin: 0; }
        .net-item { padding: 8px 12px; border-bottom: 1px solid var(--panel-border); }
        .net-item:last-child { border-bottom: none; }
        .net-name { font-weight: 500; color: var(--accent); }
        .node { display: inline-block; background: rgba(160, 160, 160, 0.2); padding: 2px 8px; border-radius: 4px; margin: 2px; font-size: 12px; }
        .violation { padding: 10px 12px; margin-bottom: 8px; border-radius: 4px; border-left: 3px solid; }
        .violation-error { border-color: var(--error); background: rgba(239, 68, 68, 0.1); }
        .violation-warning { border-color: var(--warning); background: rgba(245, 159, 7, 0.1); }
        .violation-info { border-color: var(--info); background: rgba(59, 130, 246, 0.1); }
        .severity-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase; }
        .severity-error { background: var(--error); color: #000; }
        .severity-warning { background: var(--warning); color: #000; }
        .severity-info { background: var(--info); color: #000; }
    </style>
</head>
<body>""")
    
    # Header
    parts.append(f"""<div class="header">
    <h1>Nexus-EDA Netlist Viewer</h1>
    <div class="header-stats">
        <div class="stat"><span class="stat-label">Version:</span> <span class="stat-value">{netlist.version or '(unspecified)'}</span></div>
        <div class="stat"><span class="stat-label">Components:</span> <span class="stat-value">{len(netlist.components)}</span></div>
        <div class="stat"><span class="stat-label">Nets:</span> <span class="stat-value">{len(netlist.nets)}</span></div>
    </div>
</div>""")
    
    # Components
    if config.show_components and netlist.components:
        parts.append('<div class="section"><div class="section-title">Components</div><table>')
        parts.append('<thead><tr><th>Ref</th><th>Value</th><th>Footprint</th></tr></thead><tbody>')
        for ref, fields in sorted(netlist.components.items()):
            value = fields.get('Value', '?')
            footprint = fields.get('Footprint', 'N/A')
            parts.append(f'<tr><td>{ref}</td><td>{value}</td><td>{footprint}</td></tr>')
        parts.append('</tbody></table></div>')
    
    # Nets
    if config.show_nets and netlist.nets:
        parts.append('<div class="section"><div class="section-title">Nets</div><ul class="net-list">')
        display_nets = list(netlist.nets.items())[:config.max_nets_display]
        for net_name, nodes in display_nets:
            cls = ' selected' if config.selected_net == net_name else ''
            parts.append(f'<li class="net-item{cls}"><div class="net-name">{net_name}</div><div class="net-nodes">')
            for node in nodes:
                parts.append(f'<span class="node">{node}</span>')
            parts.append('</div></li>')
        if len(netlist.nets) > config.max_nets_display:
            remaining = len(netlist.nets) - config.max_nets_display
            parts.append(f'<li class="net-item"><div class="net-nodes">... and {remaining} more nets</div></li>')
        parts.append('</ul></div>')
    
    # Validation
    if config.show_validation and violations:
        parts.append('<div class="section"><div class="section-title">Validation Results</div>')
        for v in violations:
            target = v.component or v.net or ''
            parts.append(f'<div class="violation violation-{v.severity}">')
            parts.append(f'<span class="severity-badge severity-{v.severity}">{v.severity}</span>')
            parts.append(f' <strong>{v.rule_id}</strong>: {v.description}')
            if target:
                parts.append(f' <span style="color: var(--accent);">[{target}]</span>')
            parts.append('</div>')
        parts.append('</div>')
    
    # Footer
    parts.append('</body></html>')
    
    return "\n".join(parts)


def render_validation_results_html(
    violations: List[ValidationResult],
    title: str = "Validation Results"
) -> str:
    """Render validation results as a compact HTML panel."""
    parts = [f'<div class="section"><div class="section-title">{title}</div>']
    
    if not violations:
        parts.append('<div style="color: var(--success); padding: 12px;">&#10003; No violations found</div>')
    else:
        for v in violations:
            target = v.component or v.net or ''
            parts.append(f'<div class="violation violation-{v.severity}">')
            parts.append(f'<span class="severity-badge severity-{v.severity}">{v.severity}</span>')
            parts.append(f' <strong>{v.rule_id}</strong>: {v.description}')
            if target:
                parts.append(f' <span style="color: var(--accent);">[{target}]</span>')
            if v.details:
                parts.append(f'<div style="color: var(--text-secondary); font-size: 12px; margin-top: 4px;">{v.details}</div>')
            parts.append('</div>')
    
    parts.append('</div>')
    return "\n".join(parts)