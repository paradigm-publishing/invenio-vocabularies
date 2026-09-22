# SPDX-FileCopyrightText: 2020-2024 CERN.
# SPDX-FileCopyrightText: 2024 Uni Münster.
# SPDX-License-Identifier: MIT

"""Vocabularies admin interface."""

from functools import partial

from flask import abort, current_app, url_for
from invenio_administration.views.base import (
    AdminResourceDetailView,
    AdminResourceListView,
)
from invenio_i18n import lazy_gettext as _
from invenio_records_resources.proxies import current_service_registry
from invenio_search_ui.searchconfig import SearchAppConfig, SortConfig

from ...proxies import current_service
from ...records.models import VocabularyType

GENERIC_VOCABULARY_FIELDS = "*"
"""Key holding the fields used for vocabulary types without an entry of their own."""


class VocabulariesListView(AdminResourceListView):
    """Configuration for vocabularies list view."""

    api_endpoint = "/vocabularies/"
    name = "vocabulary-types"
    menu_label = _("Vocabulary Types")
    resource_config = "vocabulary_admin_resource"
    search_request_headers = {"Accept": "application/json"}
    title = _("Vocabulary Types")
    category = _("Site management")

    pid_path = "id"
    icon = "exchange"
    template = "invenio_administration/search.html"

    display_search = True
    display_delete = False
    display_edit = False
    display_create = False

    item_field_list = {
        "id": {"text": _("Name"), "order": 1},
        "count": {"text": _("Number of entries"), "order": 2},
    }

    search_config_name = "VOCABULARIES_TYPES_SEARCH"
    search_facets_config_name = "VOCABULARIES_TYPES_FACETS"
    search_sort_config_name = "VOCABULARIES_TYPES_SORT_OPTIONS"


class VocabularyItemsViewMixin:
    """Scopes an administration view to the items of one vocabulary type.

    Items of a vocabulary type are not served by the vocabularies admin
    resource but by the resource of the type itself: generic types by
    ``/api/vocabularies/<type>``, custom ones (names, awards, ...) by their own
    top-level endpoint. Everything that depends on the type - API endpoint,
    schema, displayed fields, sort options - is therefore resolved per request
    from the service registered for that type, rather than restated in
    configuration.

    Subclasses do so by overriding the hooks the administration views already
    call (``get_api_endpoint``, ``get_service_schema``, ``item_field_list``,
    ...), so that the context itself is still built by the parent view.
    """

    #: `vocabulary_admin_resource` only satisfies the administration view
    #: machinery; item data is fetched from the type's own resource.
    resource_config = "vocabulary_admin_resource"

    #: The localized representation, so that the i18n `title` of a vocabulary
    #: item is rendered in the user's language instead of a fixed one.
    request_headers = {"Accept": "application/vnd.inveniordm.v1+json"}
    search_request_headers = {"Accept": "application/vnd.inveniordm.v1+json"}

    pid_path = "id"
    resource_name = "id"

    display_create = False
    display_delete = False
    display_edit = False

    #: Vocabulary type the view is scoped to, set from the URL on every
    #: request. Flask builds one view instance per request, see
    #: `flask.views.View.init_every_request`.
    type_id = None

    @property
    def is_custom_vocabulary(self):
        """Check whether the type is served by its own top-level resource."""
        return self.type_id in current_app.config.get(
            "VOCABULARIES_CUSTOM_VOCABULARY_TYPES", []
        )

    @property
    def item_service(self):
        """Service serving the items of the vocabulary type."""
        if self.is_custom_vocabulary:
            return current_service_registry.get(self.type_id)
        return current_service

    @property
    def vocabulary_title(self):
        """Human readable name of the vocabulary type."""
        metadata = current_app.config.get("INVENIO_VOCABULARY_TYPE_METADATA", {})
        return metadata.get(self.type_id, {}).get(
            "name", self.type_id.capitalize() if self.type_id else ""
        )

    def scope_to_vocabulary_type(self, type_id):
        """Scope the view to ``type_id``, aborting if it does not exist."""
        self.type_id = type_id
        if not self.is_custom_vocabulary:
            if VocabularyType.query.filter_by(id=type_id).one_or_none() is None:
                abort(404)

    def item_fields(self, view):
        """Fields displayed by ``view``, either ``list`` or ``details``."""
        config = current_app.config["VOCABULARIES_ADMINISTRATION_ITEM_FIELDS"]
        return config.get(self.type_id, config[GENERIC_VOCABULARY_FIELDS])[view]

    def items_ui_endpoint(self):
        """Administration UI endpoint listing the items of the type."""
        return url_for(
            f"administration.{VocabularyItemsListView.name}", pid_value=self.type_id
        )

    def get_api_endpoint(self, **kwargs):
        """REST API endpoint serving the items of the type."""
        api_url_prefix = current_app.config["SITE_API_URL"]
        if self.is_custom_vocabulary:
            return f"{api_url_prefix}/{self.type_id}"
        return f"{api_url_prefix}/vocabularies/{self.type_id}"

    def get_service_schema(self):
        """Schema of the items, which differs from one vocabulary type to the next.

        Overrides the parent's classmethod; it is only ever called on an
        instance, as the views leave `schema` unset.
        """
        schema = self.item_service.schema.schema
        # invenio-records-resources>=11.1 already wraps an instance.
        return schema() if isinstance(schema, type) else schema

    def get_list_view_endpoint(self):
        """Items of this type, which rows and "back to list" point to.

        Without this, both would point at the vocabulary types list and rows
        would link to ``<types list>/<item id>``, reading the item's id as the
        id of a vocabulary type.
        """
        return self.items_ui_endpoint()


class VocabularyItemsListView(VocabularyItemsViewMixin, AdminResourceListView):
    """List view of the items of a single vocabulary type."""

    name = "vocabulary-type-items"
    url = "/vocabulary-types/<pid_value>"
    template = "invenio_administration/search.html"

    #: Reached from the vocabulary types list, so it has no menu entry of its
    #: own. Note that `disabled` is only honoured when it is callable.
    disabled = lambda _: True

    display_read = True
    display_search = True

    @property
    def title(self):
        """Title of the page."""
        return self.vocabulary_title

    @property
    def item_field_list(self):
        """Columns of the items table."""
        return self.item_fields("list")

    def init_search_config(self, **kwargs):
        """Build the search config from the search options of the type's service."""
        search_opts = self.item_service.config.search
        sort_options = search_opts.sort_options

        return partial(
            SearchAppConfig.generate,
            dict(
                endpoint=self.get_api_endpoint(**kwargs),
                headers=self.get_search_request_headers(**kwargs),
                grid_view=False,
                # Sorting is validated against the service's own options, so
                # offering anything else here would only produce errors.
                sort=SortConfig(
                    sort_options,
                    list(sort_options),
                    search_opts.sort_default,
                    search_opts.sort_default_no_query,
                ),
                pagination_options=(20, 50),
                default_size=20,
            ),
        )

    def get(self, **kwargs):
        """GET view method."""
        self.scope_to_vocabulary_type(kwargs.get("pid_value", ""))
        return super().get(**kwargs)


class VocabularyItemDetailsView(VocabularyItemsViewMixin, AdminResourceDetailView):
    """Read-only details view of a single vocabulary item."""

    name = "vocabulary-type-item-details"
    #: Item ids are not necessarily URL-safe (e.g. subjects are identified by
    #: a URL), hence the `path` converter.
    url = "/vocabulary-types/<type_id>/<path:pid_value>"
    template = "invenio_administration/details.html"

    pid_value = None

    @property
    def title(self):
        """Title of the page."""
        return f"{self.vocabulary_title} / {self.pid_value}"

    @property
    def item_field_list(self):
        """Rows of the item details table."""
        return self.item_fields("details")

    def get(self, type_id=None, pid_value=None):
        """GET view method."""
        self.scope_to_vocabulary_type(type_id)
        self.pid_value = pid_value
        return super().get(pid_value=pid_value)
