# Kimina client

Client SDK to interact with Kimina Lean server. 

Example use:
```python
from kimina_client import KiminaClient

# Specify LEAN_SERVER_API_KEY in your .env or pass `api_key`.
# Default `api_url` is https://projectnumina.ai
client = KiminaClient()

# If running locally use:
# client = KiminaClient(api_url="http://localhost:80")

client.check("#check Nat")
```

### AST endpoints

```python
from kimina_client import KiminaClient

client = KiminaClient()

# Get AST for existing modules
mod_res = client.ast(["Mathlib", "Lean.Elab.Frontend"])  # POST /api/ast
print(mod_res.results[0].module, mod_res.results[0].error)

# Get AST from raw code
code = """import Mathlib
#check Nat
"""
code_res = client.ast_code(code, module="User.Code")  # POST /api/ast_code
print(code_res.results[0].module, code_res.results[0].ast is not None)
```

## Backward client

```python
from kimina_client import Lean4Client

client = Lean4Client()

client.verify("#check Nat")
```