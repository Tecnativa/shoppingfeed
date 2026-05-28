# Copyright 2025 Juan Carlos Oñate - Tecnativa <juancarlos.onate@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import requests

from odoo import api, fields, models
from odoo.exceptions import AccessError


class ShoppingfeedStore(models.Model):
    _name = "shoppingfeed.store"
    _inherit = ["mail.thread"]
    _description = "Shoppingfeed Store Configuration"

    name = fields.Char()
    country_id = fields.Many2one("res.country", string="Country")
    company_id = fields.Many2one(
        comodel_name="res.company", default=lambda self: self.env.company, required=True
    )
    username = fields.Char(required=True)
    password = fields.Char(required=True)
    access_token = fields.Char(readonly=True)
    token_type = fields.Char(readonly=True)
    catalog_id = fields.Char(string="Store ID (Catalog)", tracking=True)
    channel_ids = fields.One2many(
        comodel_name="shoppingfeed.channel",
        inverse_name="store_id",
        string="Channels",
        tracking=True,
    )
    marketplace_customer_group_ids = fields.One2many(
        comodel_name="shoppingfeed.store.order.type.map",
        inverse_name="store_id",
        string="Marketplace Customer Groups",
    )
    lang_id = fields.Many2one("res.lang", string="Language", tracking=True)
    email = fields.Char(string="Account Email")
    status = fields.Char(string="Store Status", tracking=True)
    website_id = fields.Many2one(
        comodel_name="website",
        string="Canonical Website",
        help=(
            "Website used to build product, category and image URLs in the "
            "catalog feed (and the feed URL itself). If empty, the system "
            "falls back to the global 'web.base.url' parameter and to the "
            "host the request comes from."
        ),
    )
    feed_url = fields.Char(
        string="Catalog Feed URL",
        compute="_compute_feed_url",
        readonly=True,
        tracking=True,
    )
    export_only_selected = fields.Boolean(
        help="If enabled, only products explicitly marked with "
        "'Export To Shoppingfeed' will be exported in the catalog feed.",
        default=True,
        tracking=True,
    )
    export_type_goods = fields.Boolean(
        string="Goods",
        default=True,
        help="Include goods products (type = 'consu') in the Shoppingfeed export.",
    )
    export_type_service = fields.Boolean(
        string="Services",
        default=False,
        tracking=True,
        help="Include service products (type = 'service') in the Shoppingfeed export.",
    )
    export_type_combo = fields.Boolean(
        string="Combos",
        default=False,
        tracking=True,
        help="Include combo products (type = 'combo') in the Shoppingfeed export.",
    )
    export_out_of_stock = fields.Boolean(
        string="Export Out of Stock Products",
        default=True,
        tracking=True,
        help=(
            "If enabled, products with no stock (quantity <= 0) will be included "
            "in the Shoppingfeed export."
        ),
    )
    export_disabled_products = fields.Boolean(
        default=False,
        tracking=True,
        help=(
            "If enabled, include archived (inactive) products in the "
            "Shoppingfeed export."
        ),
    )
    export_not_salable_products = fields.Boolean(
        default=False,
        tracking=True,
        help=(
            "If enabled, include products not allowed for sale (sale_ok = False) "
            "in the Shoppingfeed export."
        ),
    )
    use_actual_stock_state = fields.Boolean(
        default=True,
        tracking=True,
        help=(
            "If enabled, real stock quantities will be used for products that "
            "manage stock. Products without stock management will use the "
            "default quantity."
        ),
    )
    quantity_type = fields.Selection(
        [
            ("salable", "Salable Quantity"),
            ("virtual", "Virtual Quantity"),
        ],
        default="salable",
        tracking=True,
        help=(
            "Choose which stock quantity to export: "
            "'Salable' uses qty_available, 'Virtual' uses virtual_available."
        ),
    )
    default_quantity = fields.Integer(
        default=100,
        tracking=True,
        help=(
            "Default quantity to use for products that do not manage stock or "
            "when real stock is not used."
        ),
    )
    force_zero_quantity_non_salable = fields.Boolean(
        string="Force Zero Quantity for Non Salable Products",
        default=False,
        tracking=True,
        help=(
            "If enabled, products that are not allowed for sale (sale_ok=False) "
            "will be exported with quantity 0."
        ),
    )
    update_quantities_realtime = fields.Boolean(
        string="Update Quantities in Real Time",
        default=True,
        tracking=True,
        help=(
            "If enabled, product quantities will be pushed to Shoppingfeed immediately "
            "when stock changes are detected. "
            "This may slow down inventory updates."
        ),
    )
    update_prices_realtime = fields.Boolean(
        string="Update Prices in Real Time",
        default=True,
        tracking=True,
        help=(
            "If enabled, product prices will be pushed to Shoppingfeed immediately "
            "when price changes are detected."
        ),
    )
    pricelist_id = fields.Many2one(
        comodel_name="product.pricelist",
        string="Pricelist for Shoppingfeed Export",
        tracking=True,
        help="Pricelist used to compute prices during Shoppingfeed export.",
    )
    include_taxes_in_price = fields.Boolean(
        string="Include Taxes in Price",
        default=False,
        tracking=True,
        help="If enabled, the exported price will include customer taxes.",
    )
    export_price_without_tax = fields.Boolean(
        string="Export Price Without Tax as Attribute",
        default=False,
        tracking=True,
        help="If enabled, the price without tax will be added as an attribute.",
    )
    price_without_tax_attribute_name = fields.Char(
        string="Attribute Name for Price Without Tax",
        default="price_without_tax",
        tracking=True,
        help="Name of the attribute for the price without tax.",
    )
    additional_pricelist_ids = fields.Many2many(
        comodel_name="product.pricelist",
        relation="shoppingfeed_store_pricelist_rel",
        column1="store_id",
        column2="pricelist_id",
        string="Additional Pricelists",
        tracking=True,
        help="Additional pricelists to export as price attributes in the catalog.",
    )
    use_product_id_as_sku = fields.Boolean(
        string="Use Product ID for SKU",
        default=False,
        tracking=True,
        help=(
            "If enabled, the internal product ID will be used as the SKU in the feed, "
            "instead of the product's Default Code."
        ),
    )
    custom_sku_field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        string="Custom SKU Attribute",
        domain="[('model', '=', 'product.product'), ('ttype', 'in', ['char', 'text'])]",
        tracking=True,
        help=(
            "Select field from product.product to be used as the SKU in the export. "
            "Leave empty to use the default behavior (Default Code or Product ID)."
        ),
    )
    additional_attribute_field_ids = fields.One2many(
        comodel_name="shoppingfeed.store.attribute.field",
        inverse_name="store_id",
        string="Additional Attributes",
        help=(
            "Select one or more fields from product.product to include as "
            "additional attributes in the exported Shoppingfeed catalog. "
            "You can customize the attribute name for each field."
        ),
    )
    # TODO: Currently has no effect unless a custom attribute set field exists.
    export_attribute_set_name = fields.Boolean(
        default=False,
        tracking=True,
        help=(
            "If enabled, include the attribute set name in the exported catalog feed. "
            "Currently has no effect unless a custom attribute set field exists."
        ),
    )
    export_all_images = fields.Boolean(
        default=True,
        tracking=True,
        help=(
            "If enabled, all images of the product will be exported. "
            "If disabled, only the main image or the number defined "
            "in 'Exported Image Count' will be included in the feed."
        ),
    )
    exported_image_count = fields.Integer(
        default=1,
        tracking=True,
        help=(
            "Number of images to export per product when 'Export All Images' "
            "is disabled."
        ),
    )
    allowed_categ_ids = fields.Many2many(
        comodel_name="product.public.category",
        string="Category Selection",
        help="Select which product categories will be exported to Shoppingfeed.",
    )
    import_orders = fields.Boolean(
        default=True,
        tracking=True,
        help="If enabled, orders from Shoppingfeed will be imported automatically.",
    )
    default_order_type_id = fields.Many2one(
        comodel_name="sale.order.type",
        string="Default Order Type",
        tracking=True,
        help=(
            "Default Sale Order Type to assign to imported orders when no other type "
            "is detected or explicitly set from the Shoppingfeed source."
        ),
    )
    default_payment_mode_id = fields.Many2one(
        comodel_name="account.payment.mode",
        string="Default Payment Mode",
        tracking=True,
        help="Default payment mode to assign to orders when no other is provided.",
    )
    default_payment_term_id = fields.Many2one(
        comodel_name="account.payment.term",
        string="Default Payment Terms",
        tracking=True,
        help="Default payment terms to assign to orders when no other is provided.",
    )
    carrier_map_ids = fields.One2many(
        comodel_name="shoppingfeed.store.carrier.map",
        inverse_name="store_id",
        string="Carrier Mappings",
    )
    default_delivery_carrier_id = fields.Many2one(
        comodel_name="delivery.carrier",
        string="Default Delivery Carrier",
        help=(
            "Default carrier to assign to imported orders "
            "when the carrier from Shoppingfeed is not mapped."
        ),
    )
    notify_shipment = fields.Boolean(
        string="Notify Shipment to ShoppingFeed",
        default=True,
        tracking=True,
        help=(
            "If enabled, shipment notifications will be sent to ShoppingFeed "
            "when orders are shipped."
        ),
    )
    demo_mode = fields.Boolean(
        default=False,
        copy=False,
        tracking=True,
        help=(
            "When active, ALL outgoing write requests to the ShoppingFeed API "
            "are silently blocked: order acknowledgement, inventory updates, "
            "shipment notifications and invoice uploads are suppressed. "
            "Orders will still be imported from ShoppingFeed (GET requests "
            "are not affected). Use this to test the integration without "
            "affecting production data in ShoppingFeed."
        ),
    )
    filter_order_acknowledgment = fields.Selection(
        [
            ("acknowledged", "Acknowledged"),
            ("unacknowledged", "Unacknowledged"),
        ],
        default="unacknowledged",
        string="Filter Acknowledgment",
    )
    date_download_since = fields.Datetime()

    @api.depends("catalog_id", "website_id")
    def _compute_feed_url(self):
        for store in self:
            base_url = store.get_base_url().rstrip("/")
            store.feed_url = (
                f"{base_url}/catalog/{store.catalog_id}.xml" if store.catalog_id else ""
            )

    def action_toggle_demo_mode(self):
        self.env["res.users"].check_access_rights("write")
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(
                self.env._(
                    "Only administrators can toggle the demo mode "
                    "on a Shoppingfeed store."
                )
            )
        for store in self:
            store.demo_mode = not store.demo_mode

    def _shoppingfeed_is_demo_mode(self):
        self.ensure_one()
        return bool(self.demo_mode)

    def action_get_access_token(self):
        for store in self:
            self._authenticate_with_shoppingfeed(store)
            self._fetch_account_info(store)

    def _authenticate_with_shoppingfeed(self, store):
        payload = {
            "grant_type": "password",
            "username": store.username,
            "password": store.password,
        }
        headers = {"Content-Type": "application/json"}
        auth_response = requests.post(
            "https://api.shopping-feed.com/v1/auth",
            json=payload,
            headers=headers,
            timeout=20,
        )
        if auth_response.status_code != 200:
            raise ValueError(f"Authentication failed: {auth_response.text}")
        auth_data = auth_response.json()
        access_token = auth_data.get("access_token")
        token_type = auth_data.get("token_type")
        if not access_token:
            raise ValueError("No access token received from Shoppingfeed.")
        store.write({"access_token": access_token, "token_type": token_type})

    def _fetch_account_info(self, store):
        # Retrieve store info, language, and channels from Shoppingfeed.
        info_headers = {
            "Content-Type": "application/json",
            "Authorization": store.access_token,
        }
        info_response = requests.get(
            "https://api.shopping-feed.com/v1/me",
            headers=info_headers,
            timeout=20,
        )
        if info_response.status_code != 200:
            raise ValueError(f"Failed to retrieve account info: {info_response.text}")
        info_data = info_response.json()
        self._update_store_from_info(store, info_data, info_headers)

    def _update_store_from_info(self, store, info_data, info_headers):
        email = info_data.get("email")
        embedded = info_data.get("_embedded", {})
        stores = embedded.get("store", [])
        if not stores:
            return
        sf_store = stores[0]
        catalog_id = str(sf_store.get("id"))
        country_code = sf_store.get("country")
        name = sf_store.get("name")
        status = sf_store.get("status")
        country = self.env["res.country"].search([("code", "=", country_code)], limit=1)
        store.write(
            {
                "catalog_id": catalog_id,
                "name": name or store.name,
                "status": status,
                "country_id": country.id if country else False,
                "email": email,
            }
        )
        self._fetch_and_update_channels(store, sf_store, info_headers)

    def _fetch_and_update_channels(self, store, sf_store, info_headers):
        # Fetch and update installed channels for this store.
        channel_link = sf_store.get("_links", {}).get("channel", {}).get("href")
        if not channel_link:
            return
        if not channel_link.startswith("http"):
            channel_link = f"https://api.shopping-feed.com{channel_link}"
        channel_response = requests.get(channel_link, headers=info_headers, timeout=20)
        if channel_response.status_code != 200:
            return
        data = channel_response.json()
        store_channels = data.get("_embedded", {}).get("storeChannel", [])
        # Collect installed channel names from API
        installed_names = {
            channel_data["name"]
            for sc in store_channels
            if sc.get("installed")
            for channel_data in [sc.get("_embedded", {}).get("channel", {})]
            if channel_data.get("name")
        }
        Channel = self.env["shoppingfeed.channel"].sudo()
        # Create channels that don't exist yet for this store (matched by API name)
        existing_api_names = set(store.channel_ids.mapped("sf_channel_name"))
        for api_name in installed_names:
            if api_name not in existing_api_names:
                Channel.create(
                    {
                        "name": api_name,
                        "sf_channel_name": api_name,
                        "store_id": store.id,
                    }
                )
