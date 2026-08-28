import sys
sys.path.insert(0, "src")
from nexus_eda.agents import thermal_agent as t
print("import OK")
print("classes:", [c for c in dir(t) if not c.startswith("_")])
