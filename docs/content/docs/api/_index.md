---
title: "API Reference"
weight: 60
---

# API Reference

Complete reference for the Nexus-EDA Python API.

## Core Modules

### `nexus_eda`

```python
import nexus_eda
print(nexus_eda.__version__)  # "0.1.0"
```

#### `register()`

```python
from nexus_eda import register

plugin = register()
```

Registers the plugin with KiCad's pcbnew. Returns a `NexusEDAPlugin` instance.

---

### `nexus_eda.llm.engine`

#### `LLMConfig`

```python
from nexus_eda.llm.engine import LLMConfig

class LLMConfig:
    model_id: str
    model_path: Optional[str]
    quant: str                    # "Q4_K_M"
    temperature: float            # 0.1
    top_p: float                  # 0.9
    max_tokens: int               # 4096
    context_k: int                # 128
    api_url: str                  # "http://localhost:8000"
    extra: dict
```

#### `load_model(model_path=None, config=None)`

Load or return a cached LLM engine.

```python
from nexus_eda.llm.engine import load_model

engine = load_model()  # Uses manifest defaults
engine = load_model(model_path="models/my-model.gguf")
```

#### `generate(prompt, ...)`

```python
from nexus_eda.llm.engine import generate

response = generate("Analyze this netlist: ...")
```

#### `LLMEngine`

```python
from nexus_eda.llm.engine import LLMEngine, LLMConfig

config = LLMConfig.from_manifest()
engine = LLMEngine(config=config)
engine.load()

# Streaming
for token in engine.generate_stream("Hello"):
    print(token, end="")
```

---

### `nexus_eda.netlist.parser`

#### `NetlistParser`

```python
from nexus_eda.netlist.parser import NetlistParser

parser = NetlistParser()
data = parser.parse_file("path/to/file.net")
# data is NetlistData with .components and .nets

data = parser.parse_content(s_expression_string)
```

#### `NetlistData`

```python
class NetlistData:
    version: str
    components: Dict[str, Dict]  # ref_des -> field dict
    nets: Dict[str, List[str]]   # net_name -> ["R1/1", "U1/3", ...]
```

#### `DesignRuleChecker`

```python
from nexus_eda.netlist.parser import DesignRuleChecker, NetlistData

drc = DesignRuleChecker(min_trace_width=0.25, min_clearance=0.25)
violations = drc.check_netlist(netlist_data)
```

#### `parse_netlist(filepath)`

Convenience function — equivalent to `NetlistParser().parse_file(filepath)`.

#### `validate_netlist(netlist_data, ...)`

Convenience function — runs DRC checks on parsed netlist data.

---

### `nexus_eda.plugin`

#### `NexusEDAPlugin`

```python
from nexus_eda.plugin import NexusEDAPlugin

# This is the main KiCad plugin class
# It registers with pcbnew.ActionPlugin
```

#### `NexusEDABar`

```python
from nexus_eda.plugin import NexusEDABar

# wx.Menu subclass that adds Nexus-EDA menu items to KiCad's menubar
```
