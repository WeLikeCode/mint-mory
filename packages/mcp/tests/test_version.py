"""The MCP server reports the installed distro's version, not a hardcoded one."""

from importlib.metadata import version

from mintmory.mcp.server import mcp


def test_server_version_is_the_installed_distro_version() -> None:
    assert mcp.version == version("mintmory-mcp")
