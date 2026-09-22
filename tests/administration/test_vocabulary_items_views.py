# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Tests for the vocabulary items administration views."""

import json
import re

import pytest
from invenio_records_resources.proxies import current_service_registry

from invenio_vocabularies.records.api import Vocabulary


@pytest.fixture(scope="module")
def licenses(database, search, identity, service):
    """A generic vocabulary type with a couple of items."""
    service.create_type(identity, "licenses", "lic")
    for data in [
        {"id": "cc-by", "title": {"en": "Creative Commons Attribution"}},
        {"id": "cc0", "title": {"en": "Creative Commons Zero"}},
    ]:
        service.create(identity, {**data, "type": "licenses"})
    Vocabulary.index.refresh()


def search_config(response):
    """Extract the React-SearchKit config of a rendered list view."""
    match = re.search(
        r"data-invenio-search-config='(.*?)'", response.get_data(as_text=True), re.S
    )
    assert match, "no search config rendered"
    return json.loads(match.group(1))


def details_config(response):
    """Extract the data attributes of a rendered details view."""
    html = response.get_data(as_text=True)
    return {
        key: value for key, value in re.findall(r"data-([a-z-]+)='(.*?)'\n", html, re.S)
    }


#
# List view
#
def test_list_view_of_generic_vocabulary(client_with_credentials, licenses):
    """Items of a generic type are searched on the generic vocabularies API."""
    res = client_with_credentials.get("/administration/vocabulary-types/licenses")

    assert res.status_code == 200
    config = search_config(res)
    assert config["searchApi"]["axios"]["url"].endswith("/api/vocabularies/licenses")
    # The localized representation, so that titles follow the user's locale.
    assert (
        config["searchApi"]["axios"]["headers"]["Accept"]
        == "application/vnd.inveniordm.v1+json"
    )


def test_list_view_of_custom_vocabulary(client_with_credentials):
    """Items of a custom type are searched on the type's own API."""
    res = client_with_credentials.get("/administration/vocabulary-types/names")

    assert res.status_code == 200
    assert search_config(res)["searchApi"]["axios"]["url"].endswith("/api/names")


def test_list_view_rows_link_to_the_item_details_view(
    client_with_credentials, licenses
):
    """Rows must not link back into the vocabulary types list."""
    res = client_with_credentials.get("/administration/vocabulary-types/licenses")

    assert (
        "data-list-endpoint='/administration/vocabulary-types/licenses'"
        in res.get_data(as_text=True)
    )


@pytest.mark.parametrize("vocabulary_type", ["awards", "names", "subjects"])
def test_list_view_only_offers_supported_sort_options(
    client_with_credentials, vocabulary_type
):
    """Sorting is validated by the service, so only its own options may be offered."""
    res = client_with_credentials.get(
        f"/administration/vocabulary-types/{vocabulary_type}"
    )

    assert res.status_code == 200
    config = search_config(res)
    supported = set(
        current_service_registry.get(vocabulary_type).config.search.sort_options
    )
    assert {option["sortBy"] for option in config["sortOptions"]} == supported
    assert config["initialQueryState"]["sortBy"] in supported


def test_list_view_is_not_in_the_admin_menu(client_with_credentials, licenses):
    """The view is reached from the types list, not from the sidebar."""
    res = client_with_credentials.get("/administration/vocabulary-types")

    assert res.status_code == 200
    assert "/administration/vocabulary-types/<pid_value>" not in res.get_data(
        as_text=True
    )


#
# Details view
#
def test_details_view_of_generic_vocabulary(client_with_credentials, licenses):
    """An item of a generic type is read from the generic vocabularies API."""
    res = client_with_credentials.get("/administration/vocabulary-types/licenses/cc-by")

    assert res.status_code == 200
    data = details_config(res)
    assert data["api-endpoint"].endswith("/api/vocabularies/licenses")
    assert json.loads(data["pid"]) == "cc-by"
    # Back to the items of this type, not to the vocabulary types list.
    assert data["list-endpoint"] == "/administration/vocabulary-types/licenses"


def test_details_view_of_custom_vocabulary(client_with_credentials):
    """An item of a custom type is read from the type's own API."""
    res = client_with_credentials.get(
        "/administration/vocabulary-types/names/0000-0001-8135-3489"
    )

    assert res.status_code == 200
    data = details_config(res)
    assert data["api-endpoint"].endswith("/api/names")
    assert json.loads(data["pid"]) == "0000-0001-8135-3489"


def test_details_view_accepts_url_shaped_ids(client_with_credentials):
    """Subjects and similar vocabularies identify their items by URL."""
    res = client_with_credentials.get(
        "/administration/vocabulary-types/subjects/https://id.nlm.nih.gov/mesh/D000001"
    )

    assert res.status_code == 200
    data = details_config(res)
    assert json.loads(data["pid"]) == "https://id.nlm.nih.gov/mesh/D000001"
    assert data["api-endpoint"].endswith("/api/subjects")


def test_details_view_is_read_only(client_with_credentials, licenses):
    """Editing and deleting vocabulary items is not offered."""
    res = client_with_credentials.get("/administration/vocabulary-types/licenses/cc-by")

    data = details_config(res)
    assert json.loads(data["display-edit"]) is False
    assert json.loads(data["display-delete"]) is False


#
# Vocabulary types list view
#
def test_types_list_view_only_offers_supported_sort_options(
    app, client_with_credentials
):
    """Sort options the types service ignores would silently do nothing."""
    res = client_with_credentials.get("/administration/vocabulary-types")

    assert res.status_code == 200
    config = search_config(res)
    types_service = app.extensions["invenio-vocabularies"].vocabulary_types_service
    supported = set(types_service.config.search.sort_options)
    assert {option["sortBy"] for option in config["sortOptions"]} <= supported


#
# Unknown vocabulary types
#
@pytest.mark.parametrize(
    "url",
    [
        "/administration/vocabulary-types/no-such-type",
        "/administration/vocabulary-types/no-such-type/some-item",
    ],
)
def test_unknown_vocabulary_type_is_not_found(client_with_credentials, url):
    """A type that does not exist must not render an empty, broken page."""
    assert client_with_credentials.get(url).status_code == 404
