"""
Tests for manifest.yaml validation.

Validates:
1. All string fields (name, version, author, description) are non-empty and under 256 characters
2. The version field follows semantic versioning (MAJOR.MINOR.PATCH) format
3. The file can be loaded as valid YAML
"""

import os
import re

import yaml

MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "..", "manifest.yaml")

# Semantic versioning pattern: MAJOR.MINOR.PATCH where each is a non-negative integer
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")

# Fields that must be non-empty strings with max 256 characters
REQUIRED_STRING_FIELDS = ["name", "version", "author"]

# Fields that can be either a string or an i18n object (dict with en_US key)
I18N_OR_STRING_FIELDS = ["description"]


def load_manifest():
    """Load and parse the manifest.yaml file."""
    with open(MANIFEST_PATH, "r") as f:
        return yaml.safe_load(f)


class TestManifestYAMLValidity:
    """Test that the manifest file is valid YAML."""

    def test_manifest_file_exists(self):
        assert os.path.isfile(MANIFEST_PATH), f"manifest.yaml not found at {MANIFEST_PATH}"

    def test_manifest_loads_as_valid_yaml(self):
        manifest = load_manifest()
        assert manifest is not None, "manifest.yaml parsed as empty/null"
        assert isinstance(manifest, dict), "manifest.yaml root should be a mapping"


class TestManifestStringFields:
    """Test that required string fields are non-empty and within 256 characters."""

    def test_required_fields_exist(self):
        manifest = load_manifest()
        for field in REQUIRED_STRING_FIELDS:
            assert field in manifest, f"Field '{field}' is missing from manifest.yaml"

    def test_fields_are_non_empty_strings(self):
        manifest = load_manifest()
        for field in REQUIRED_STRING_FIELDS:
            value = manifest[field]
            assert isinstance(value, str), (
                f"Field '{field}' should be a string, got {type(value).__name__}"
            )
            assert len(value.strip()) > 0, f"Field '{field}' must not be empty or whitespace-only"
        # Check i18n fields (can be string or dict with en_US)
        for field in I18N_OR_STRING_FIELDS:
            value = manifest[field]
            if isinstance(value, str):
                assert len(value.strip()) > 0, f"Field '{field}' must not be empty or whitespace-only"
            elif isinstance(value, dict):
                assert "en_US" in value, f"Field '{field}' as i18n object must have 'en_US' key"
                assert len(value["en_US"].strip()) > 0, f"Field '{field}.en_US' must not be empty"
            else:
                assert False, f"Field '{field}' should be a string or i18n object, got {type(value).__name__}"

    def test_fields_are_within_max_length(self):
        manifest = load_manifest()
        max_length = 256
        for field in REQUIRED_STRING_FIELDS:
            value = manifest[field]
            assert len(value) <= max_length, (
                f"Field '{field}' exceeds {max_length} characters (length: {len(value)})"
            )
        for field in I18N_OR_STRING_FIELDS:
            value = manifest[field]
            if isinstance(value, str):
                assert len(value) <= max_length, (
                    f"Field '{field}' exceeds {max_length} characters (length: {len(value)})"
                )
            elif isinstance(value, dict):
                for locale, text in value.items():
                    assert len(text) <= max_length, (
                        f"Field '{field}.{locale}' exceeds {max_length} characters (length: {len(text)})"
                    )


class TestManifestVersion:
    """Test that the version follows MAJOR.MINOR.PATCH format."""

    def test_version_follows_semver_format(self):
        manifest = load_manifest()
        version = manifest["version"]
        assert SEMVER_PATTERN.match(version), (
            f"Version '{version}' does not follow MAJOR.MINOR.PATCH format"
        )

    def test_version_components_are_non_negative_integers(self):
        manifest = load_manifest()
        version = manifest["version"]
        parts = version.split(".")
        assert len(parts) == 3, f"Version should have exactly 3 parts, got {len(parts)}"
        for i, part in enumerate(parts):
            assert part.isdigit(), f"Version component {i} ('{part}') is not a valid integer"
            assert int(part) >= 0, f"Version component {i} must be non-negative"
