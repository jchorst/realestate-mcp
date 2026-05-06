import importlib

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "realestate_mcp.servers.airbnb.server",
        "realestate_mcp.servers.carolinadesigns.server",
        "realestate_mcp.servers.loopnet.server",
        "realestate_mcp.servers.sunrealty.server",
        "realestate_mcp.servers.surforsound.server",
        "realestate_mcp.servers.twiddy.server",
    ],
)
def test_server_module_imports(module: str) -> None:
    mod = importlib.import_module(module)
    assert hasattr(mod, "main")
    assert hasattr(mod, "mcp")
