import importlib

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "realestate_mcp.servers.airbnb.server",
        "realestate_mcp.servers.loopnet.server",
        "realestate_mcp.servers.vrbo.server",
        "realestate_mcp.servers.zillow.server",
    ],
)
def test_server_module_imports(module: str) -> None:
    mod = importlib.import_module(module)
    assert hasattr(mod, "main")
    assert hasattr(mod, "mcp")
