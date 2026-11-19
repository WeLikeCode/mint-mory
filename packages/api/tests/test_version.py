"""The API reports the installed distro's version, not a hardcoded one."""

from importlib.metadata import version

from mintmory.api.app import app


def test_app_version_is_the_installed_distro_version() -> None:
    assert app.version == version("mintmory-api")
    assert app.openapi()["info"]["version"] == version("mintmory-api")
