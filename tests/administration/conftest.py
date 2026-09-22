# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Pytest configuration for the administration views.

The administration panel is served by the UI application, so these tests
override the API application used by the rest of the test suite.
"""

import pytest
from flask_webpackext.manifest import (
    JinjaManifest,
    JinjaManifestEntry,
    JinjaManifestLoader,
)
from invenio_app.factory import create_ui


class MockJinjaManifest(JinjaManifest):
    """Manifest resolving every entry to nothing."""

    def __getitem__(self, key):
        """Get a manifest entry."""
        return JinjaManifestEntry(key, [])


class MockManifestLoader(JinjaManifestLoader):
    """Loader for a manifest that does not need built assets."""

    def load(self, filepath):
        """Load the mocked manifest."""
        return MockJinjaManifest()


@pytest.fixture(scope="module")
def app_config(app_config):
    """Application configuration, without built assets."""
    app_config["WEBPACKEXT_MANIFEST_LOADER"] = MockManifestLoader
    return app_config


@pytest.fixture(scope="module")
def create_app(instance_path, entry_points):
    """UI application factory fixture."""
    return create_ui
