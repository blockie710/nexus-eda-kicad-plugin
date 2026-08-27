# SPDX-License-Identifier: Apache-2.0
"""KiCad plugin entry point and UI dialog.

Phase 1: Stubs for netlist analysis, BOM optimization, and routing suggestions.
Phase 2 (T2-W5.2): DRC agent integrated into the plugin menu.
"""

import pcbnew
import wx


class NexusEDABar(wx.Menu):
    """Top-level menu entry for Nexus-EDA within KiCad."""

    def __init__(self, board_window):
        super().__init__()
        self.board_window = board_window
        self._build_menu()

    def _build_menu(self):
        netlist_item = self.Append(
            wx.ID_ANY, "Analyze Netlist", "Run AI netlist analysis"
        )
        self.Bind(wx.EVT_MENU, self._on_analyze_netlist, netlist_item)

        bom_item = self.Append(
            wx.ID_ANY, "Optimize BOM", "AI BOM optimization against LCSC/JLCPCB"
        )
        self.Bind(wx.EVT_MENU, self._on_optimize_bom, bom_item)

        route_item = self.Append(
            wx.ID_ANY, "Suggest Routing", "AI routing suggestions for selected net"
        )
        self.Bind(wx.EVT_MENU, self._on_suggest_routing, route_item)

        # Phase 2: DRC agent (T2-W5.2)
        drc_item = self.Append(
            wx.ID_ANY, "Run DRC Check", "AI-assisted DRC violation analysis"
        )
        self.Bind(wx.EVT_MENU, self._on_run_drc, drc_item)

    def _on_analyze_netlist(self, event):
        from .agents import analyze_netlist

        board = pcbnew.GetBoard()
        result = analyze_netlist(board)
        wx.MessageBox(
            f"Netlist analysis complete.\n\n"
            f"Unrouted nets: {result.unrouted_count}\n"
            f"Warning: {result.severity} issues found",
            "Nexus-EDA",
            wx.OK | wx.ICON_INFORMATION,
        )

    def _on_optimize_bom(self, event):
        from .agents import optimize_bom

        board = pcbnew.GetBoard()
        result = optimize_bom(board)
        wx.MessageBox(
            f"BOM optimization complete.\n\n"
            f"Savings: ${result.total_savings:.2f}/board\n"
            f"Alternatives found: {result.alternatives_count}",
            "Nexus-EDA",
            wx.OK | wx.ICON_INFORMATION,
        )

    def _on_suggest_routing(self, event):
        from .agents import suggest_routing

        board = pcbnew.GetBoard()
        result = suggest_routing(board)
        wx.MessageBox(
            f"Routing suggestion:\n{result.path_description}",
            "Nexus-EDA",
            wx.OK | wx.ICON_INFORMATION,
        )

    def _on_run_drc(self, event):
        """Phase 2 (T2-W5.2): Run the DRC agent on the current board."""
        from .agents import DRCAgent, run_drc

        board = pcbnew.GetBoard()
        agent = DRCAgent(board=board)
        report = agent.run_pcbnew_drc(min_clearance=0.15)

        if report.total_count == 0:
            msg = "No DRC violations found. Board passes all checks."
        else:
            msg = (
                f"DRC Check Complete\n\n"
                f"Total violations: {report.total_count}\n"
                f"  Errors:   {report.error_count}\n"
                f"  Warnings: {report.warning_count}\n"
                f"  Info:     {report.info_count}\n\n"
                f"Severity: {report.severity.upper()}\n\n"
                f"Top issues:\n"
                + "\n".join(
                    f"  [{v.severity.value}] {v.description}"
                    for v in report.violations[:5]
                )
            )
        wx.MessageBox(msg, "Nexus-EDA DRC", wx.OK | wx.ICON_INFORMATION)


class NexusEDAPlugin(pcbnew.ActionPlugin):
    """KiCad plugin registration."""

    def defaults(self):
        self.name = "Nexus-EDA Copilot"
        self.category = "AI Design Assistant"
        self.description = "AI-assisted PCB design automation (local-first)"

    def Run(self):
        board_window = pcbnew.GetActiveBoard()
        if board_window is None:
            wx.MessageBox("No active board window", "Error", wx.OK | wx.ICON_ERROR)
            return
        menu = NexusEDABar(board_window)
        board_window.GetMenuBar().Append(menu, "Nexus-EDA")


def register():
    """Entry point called by KiCad plugin loader."""
    plugin = NexusEDAPlugin()
    plugin.register()
    return plugin
