#!/usr/bin/env python3
import sys
sys.path.insert(0, 'src')
from nexus_eda.agents.thermal_agent import parse_thermal_netlist, run_thermal_analysis, ThermalAgent, ComponentPower, PackageFamily, PowerMode

# Test 1: Comprehensive parser test
print("=== Test 1: Parser with various formats ===")
test_data = """
# Thermal export
U1 2.5 V=5.0 I=0.5 active QFN-48 40 125
R1 0.125 V=12.0 I=0.010 active SOT-23-3 150
R2 0.25 idle SOT-23 4.0
D1 0.7 peak DO-41
U2 3.0 V=3.3 I=0.9 active QFN-48 30 Tj=150
"""
comps = parse_thermal_netlist(test_data)
print(f'Parsed {len(comps)} components')
for c in comps:
    print(f'  {c.ref}: P={c.power}W, V={c.voltage}, I={c.current}, mode={c.mode.value}, fp={c.footprint}, copper={c.copper_area_mm2}, Tj_max={c.max_junction_temp}')

# Test 2: Hotspot detection with high power
print("\n=== Test 2: Hotspot detection ===")
comps = [
    ComponentPower(ref='U1', power=5.0, footprint='QFN-48', copper_area_mm2=40, max_junction_temp=125.0),
    ComponentPower(ref='R1', power=0.125, footprint='SOT-23-3', copper_area_mm2=15, max_junction_temp=125.0),
    ComponentPower(ref='Q1', power=10.0, footprint='TO-220', copper_area_mm2=200, max_junction_temp=150.0),
]
for c in comps:
    print(f'  {c.ref}: Tj={c.junction_temperature:.1f}C, is_hotspot={c.is_hotspot}, margin={c.margin:.1f}')

report = run_thermal_analysis(components=comps, ambient_temp=25.0)
print(f'Hottest: {report.hottest_component} at {report.hottest_temp:.1f}C')
print(f'Hotspots: {report.hotspot_count}')
for h in report.hotspots:
    print(f'  [{h.ref}] Tj={h.junction_temp:.1f}C, margin={h.margin:.1f}C, rec={h.recommendation}')

# Test 3: PackageFamily inference
print("\n=== Test 3: PackageFamily inference ===")
for fp, expected in [
    ('Package_TO_SOT_SMD:SOT-23-6', PackageFamily.SOT),
    ('Package_Deal:TSOT-23-6', PackageFamily.SOT),
    ('Package_SO:SOIC-8_3.9x4.9mm_P1.27mm', PackageFamily.SOIC),
    ('Package_QFP:LQFP-48_7x7mm_P0.5mm', PackageFamily.UNKNOWN),
    ('Package_SOT_SMD:TO-220-7_Vertical', PackageFamily.TO220),
    ('Package_SOT_SMD:TO-263-7', PackageFamily.TO263),
    ('Package_SOT_SMD:TO-252-7', PackageFamily.TO252),
    ('Package_SOD:SOD-123', PackageFamily.SOD),
]:
    actual = PackageFamily.from_footprint(fp)
    status = "OK" if actual == expected else "MISMATCH"
    print(f'  {fp} -> {actual.label} (expected {expected.label}) [{status}]')

# Test 4: PowerMode parsing
print("\n=== Test 4: PowerMode parsing ===")
for s in ['idle', 'active', 'peak', 'IDLE', 'ACTIVE', 'PEAK', 'unknown']:
    print(f'  "{s}" -> {PowerMode.from_str(s).value}')

# Test 5: LLM fallback summary (no LLM engine)
print("\n=== Test 5: Fallback summary ===")
agent = ThermalAgent(ambient_temp=25.0)
summary = agent.summarise(report)
print(summary)

# Test 6: Empty components
print("\n=== Test 6: Empty input ===")
empty_report = run_thermal_analysis(components=[], ambient_temp=25.0)
print(f'Empty report: count={empty_report.total_count}, hotspots={empty_report.hotspot_count}, severity={empty_report.severity}')

# Test 7: Components exceeding max junction temp
print("\n=== Test 7: Over-max-temperature ===")
comps_hot = [
    ComponentPower(ref='U1', power=8.0, footprint='TO-220', copper_area_mm2=100, max_junction_temp=150.0),
]
for c in comps_hot:
    print(f'  {c.ref}: Tj={c.junction_temperature:.1f}C, max={c.max_junction_temp}, margin={c.margin:.1f}')
report_hot = run_thermal_analysis(components=comps_hot, ambient_temp=25.0)
print(f'  Severity: {report_hot.severity}')
for issue in report_hot.issues:
    print(f'  Issue: {issue}')

print("\n=== All tests passed ===")
