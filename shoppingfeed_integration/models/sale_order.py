# Copyright 2025 Juan Carlos Oñate - Tecnativa <juancarlos.onate@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import json
from datetime import datetime, timezone

import requests
from markupsafe import Markup

from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    shoppingfeed_order_ref = fields.Char(
        string="Shoppingfeed Order ID",
        help="Numeric order ID from Shoppingfeed API (e.g., 21786210256).",
        copy=False,
        index=True,
        readonly=True,
    )
    shoppingfeed_reference = fields.Char(
        help="Marketplace order reference (e.g., TEST-68fb749e8cd95).",
        copy=False,
        index=True,
        readonly=True,
    )
    shoppingfeed_store_id = fields.Many2one(
        comodel_name="shoppingfeed.store",
        string="Shoppingfeed Store",
        help="The Shoppingfeed store from which this order was imported.",
        copy=False,
        readonly=True,
        index=True,
    )
    shoppingfeed_channel_id = fields.Many2one(
        comodel_name="shoppingfeed.channel",
        string="Shoppingfeed Channel",
        help="Indicates the channel from which this sales order originated.",
        copy=False,
        readonly=True,
    )
    shoppingfeed_status = fields.Char(
        readonly=True,
        help="Current status of the order in Shoppingfeed.",
        copy=False,
    )
    shoppingfeed_raw_data = fields.Text(
        readonly=True,
        copy=False,
        help="Complete JSON data received from Shoppingfeed API for this order.",
    )

    _sql_constraints = [
        (
            "unique_shoppingfeed_order_ref_by_company_store",
            "unique(shoppingfeed_order_ref, company_id, shoppingfeed_store_id)",
            "This Shoppingfeed order has already been imported!",
        ),
    ]

    def _is_shoppingfeed_disable_invoicing(self):
        return self.shoppingfeed_channel_id.disable_invoicing

    @api.depends("shoppingfeed_channel_id")
    def _compute_invoice_status(self):
        res = super()._compute_invoice_status()
        self.filtered(lambda so: so._is_shoppingfeed_disable_invoicing()).update(
            {"invoice_status": "no"}
        )
        return res

    @api.depends("shoppingfeed_channel_id")
    def _compute_amount_to_invoice(self):
        res = super()._compute_amount_to_invoice()
        for so in self.filtered(lambda so: so._is_shoppingfeed_disable_invoicing()):
            so.amount_to_invoice = 0
        return res

    def _shoppingfeed_fetch_orders(self, store):
        # Fetch only unacknowledged orders from Shoppingfeed for the given store.
        url = f"https://api.shopping-feed.com/v1/store/{store.catalog_id}/order"
        headers = {
            "Authorization": store.access_token,
            "Content-Type": "application/json",
        }
        params = {"acknowledgment": "unacknowledged", "status": "waiting_shipment"}
        response = requests.get(url, headers=headers, params=params, timeout=30)
        return response.json().get("_embedded", {}).get("order", [])

    def _shoppingfeed_prepare_partner(
        self, billing, store, channel=None, additional_fields=None
    ):
        # Always create a new billing partner from Shoppingfeed data.
        company = billing.get("company") or ""
        if company:
            name = company
            is_company = True
        else:
            first = billing.get("firstName") or ""
            last = billing.get("lastName") or ""
            name = (
                f"{first} {last}".strip()
                or billing.get("email")
                or "Shoppingfeed Customer"
            )
            is_company = False
        country = self.env["res.country"].search(
            [("code", "=", billing.get("country"))], limit=1
        )
        vals = {
            "name": name,
            "is_company": is_company,
            "email": billing.get("email"),
            "street": billing.get("street") or "",
            "street2": billing.get("street2"),
            "zip": billing.get("postalCode") or "",
            "city": billing.get("city"),
            "phone": billing.get("phone") or billing.get("mobilePhone"),
            "country_id": country.id,
            "company_id": store.company_id.id,
        }
        af = additional_fields or {}
        vat = (
            af.get("buyer_tax_registration_id")
            or af.get("mms-customer-tax-id")
            or af.get("buyer_identification_number")
            or af.get("buyer_identifier_number")
        )
        vat_valid = False
        if vat:
            vals["vat"] = vat
            if country:
                vat_valid = self._shoppingfeed_valid_vat(vat, country, is_company)
        if channel and channel.account_id:
            vals["property_account_receivable_id"] = channel.account_id.id
        if channel and channel.payment_method_line_id:
            vals["property_inbound_payment_method_line_id"] = (
                channel.payment_method_line_id.id
            )
        return (
            self.env["res.partner"]
            .with_context(no_vat_validation=not vat_valid)
            .create(vals)
        )

    @api.model
    def _shoppingfeed_valid_vat(self, vat, country, is_company):
        """Overwrite by other modules to check valid vat methods"""
        if self.env["res.partner"]._run_vat_test(vat, country, is_company) is False:
            return False
        return True

    def _shoppingfeed_prepare_shipping(self, shipping, partner, store):
        # Prepare or create delivery address for the Shoppingfeed order.
        if not shipping:
            return None
        shipping_vals = {
            "parent_id": partner.id,
            "type": "delivery",
            "name": (
                f"{shipping.get('firstName', '')} " f"{shipping.get('lastName', '')}"
            ).strip()
            or "Shipping Address",
            "street": shipping.get("street") or "",
            "street2": shipping.get("street2"),
            "zip": shipping.get("postalCode") or "",
            "city": shipping.get("city"),
            "phone": shipping.get("phone") or shipping.get("mobilePhone"),
            "email": shipping.get("email"),
            "country_id": self.env["res.country"]
            .search([("code", "=", shipping.get("country"))], limit=1)
            .id,
            "company_id": store.company_id.id,
        }
        shipping_partner = self.env["res.partner"].search(
            [
                ("parent_id", "=", partner.id),
                ("type", "=", "delivery"),
                ("street", "=", shipping_vals["street"]),
                ("zip", "=", shipping_vals["zip"]),
            ],
            limit=1,
        ) or self.env["res.partner"].with_context(no_vat_validation=True).create(
            shipping_vals
        )
        return shipping_partner

    def _shoppingfeed_clean_product_reference(self, reference):
        if not reference or "_" not in reference:
            return reference
        parts = reference.rsplit("_", 1)
        if len(parts) == 2 and len(parts[1]) == 2:
            return parts[0]
        return reference

    def _shoppingfeed_resolve_product_reference(self, item_reference, aliases=None):
        """Resolve product reference considering aliases from itemsReferencesAliases.
        When a SKU is manually edited in ShoppingFeed, the old SKU remains in the
        item reference but a mapping is created in itemsReferencesAliases pointing
        to the new SKU. This method resolves the correct SKU to use.
        """
        # Check if there's an alias for this reference
        if aliases and item_reference in aliases:
            return self._shoppingfeed_clean_product_reference(aliases[item_reference])
        # Return the cleaned original reference
        return self._shoppingfeed_clean_product_reference(item_reference)

    def _shoppingfeed_acknowledge_order(self, store, order):
        # Acknowledge the imported order to Shoppingfeed.
        if store._shoppingfeed_is_demo_mode():
            return
        url = f"https://api.shopping-feed.com/v1/store/{store.catalog_id}/order/acknowledge"
        headers = {
            "Authorization": store.access_token,
            "Content-Type": "application/json",
        }
        payload = {
            "order": [
                {
                    "id": int(order.get("id")),
                    "status": "success",
                    "acknowledgedAt": datetime.now(timezone.utc).isoformat(),
                }
            ]
        }
        requests.post(url, json=payload, headers=headers, timeout=30)

    def _create_shoppingfeed_log(self, store, order, channel, error_message):
        self.env["shoppingfeed.log"].create(
            {
                "name": order.get("reference") or f"Order {order.get('id')}",
                "store_id": store.id,
                "channel_id": channel.id if channel else False,
                "shoppingfeed_reference": order.get("reference"),
                "error_message": error_message,
            }
        )

    def _shoppingfeed_validate_products(self, order):
        # Validate that all products exist before creating the order.
        missing_products = []
        aliases = order.get("itemsReferencesAliases", {})
        for item in order.get("items", []):
            ref = item.get("reference")
            clean_ref = self._shoppingfeed_resolve_product_reference(ref, aliases)
            product = self.env["product.product"].search(
                [("default_code", "=", clean_ref)], limit=1
            )
            if not product:
                missing_products.append(clean_ref)
        return missing_products

    def _shoppingfeed_get_carrier(
        self, store, channel, carrier_name, shipping_country=None
    ):
        carrier = False
        if carrier_name:
            carrier_map = store.carrier_map_ids.filtered(
                lambda m, carrier_name=carrier_name: m.carrier_name.strip().lower()
                == carrier_name.strip().lower()
            )
            if carrier_map:
                carrier = carrier_map.delivery_carrier_id
        if not carrier:
            if channel and shipping_country and channel.country_carrier_ids:
                country_rule = channel.country_carrier_ids.filtered(
                    lambda r, c=shipping_country: r.country_id == c
                )
                if country_rule:
                    carrier = country_rule[0].delivery_carrier_id
            if not carrier:
                if channel and channel.default_delivery_carrier_id:
                    carrier = channel.default_delivery_carrier_id
                elif store.default_delivery_carrier_id:
                    carrier = store.default_delivery_carrier_id
        return carrier

    def _shoppingfeed_prepare_order_line(self, item, aliases=None):
        ref = item.get("reference")
        clean_ref = self._shoppingfeed_resolve_product_reference(ref, aliases)
        product = self.env["product.product"].search(
            [("default_code", "=", clean_ref)], limit=1
        )
        if not product:
            return False
        return {
            "product_id": product.id,
            "product_uom_qty": item.get("quantity", 1.0),
            "price_unit": item.get("price", product.list_price),
            "name": item.get("name") or product.display_name,
        }

    def _shoppingfeed_create_sale_order(
        self,
        store,
        order,
        partner,
        shipping_partner,
        sf_channel,
        order_type_id,
        carrier,
    ):
        # Create sale order and lines from Shoppingfeed data.
        ext_id = str(order.get("id"))
        currency = self.env["res.currency"].search(
            [("name", "=", order.get("payment", {}).get("currency", "EUR"))],
            limit=1,
        )
        aliases = order.get("itemsReferencesAliases", {})
        order_lines = []
        for item in order.get("items", []):
            line_vals = self._shoppingfeed_prepare_order_line(item, aliases)
            if line_vals:
                order_lines.append((0, 0, line_vals))
        sale_order = self.create(
            {
                "partner_id": partner.id,
                "partner_invoice_id": partner.id,
                "partner_shipping_id": shipping_partner.id
                if shipping_partner
                else partner.id,
                "shoppingfeed_reference": order.get("reference"),
                "currency_id": currency.id,
                "shoppingfeed_order_ref": ext_id,
                "shoppingfeed_store_id": store.id,
                "type_id": order_type_id or store.default_order_type_id.id,
                "payment_mode_id": store.default_payment_mode_id.id,
                "payment_term_id": store.default_payment_term_id.id,
                "shoppingfeed_channel_id": sf_channel.id,
                "shoppingfeed_status": order.get("status"),
                "company_id": store.company_id.id,
                "shoppingfeed_raw_data": json.dumps(
                    order, indent=2, ensure_ascii=False
                ),
                "order_line": order_lines,
            }
        )
        if carrier:
            payment = order.get("payment", {}) or {}
            shipping_cost = payment.get("shippingAmount", 0.0)
            sale_order.set_delivery_line(carrier, shipping_cost)
        link = (
            f"https://app.shopping-feed.com/v3/es/orders/detail/"
            f"{order.get('id')}?store={order.get('storeId')}"
        )
        body = Markup(
            "<p><b>Order created automatically by Shoppingfeed.</b></p>"
            f"<p><b>Marketplace:</b> {sf_channel.name or 'Unknown'}</p>"
            f"<p><a href='{link}' target='_blank'>"
            "View order in Shoppingfeed</a></p>"
        )
        sale_order.message_post(
            body=body, message_type="comment", subtype_xmlid="mail.mt_note"
        )
        return sale_order

    @api.model
    def action_import_from_shoppingfeed(self):
        stores = (
            self.env["shoppingfeed.store"]
            .sudo()
            .search(
                [
                    ("access_token", "!=", False),
                    ("catalog_id", "!=", False),
                ]
            )
        )
        for store in stores:
            self.with_company(store.company_id)._import_orders_from_shoppingfeed(store)

    def _import_orders_from_shoppingfeed(self, store):
        if not store.import_orders:
            return
        for order in self._shoppingfeed_fetch_orders(store):
            ext_id = str(order.get("id"))
            if self.search([("shoppingfeed_order_ref", "=", ext_id)], limit=1):
                continue
            channel = (order.get("_embedded") or {}).get("channel", {})
            channel_name = channel.get("name", "Unknown Marketplace")
            sf_channel = (
                self.env["shoppingfeed.channel"]
                .sudo()
                .search(
                    [
                        ("sf_channel_name", "=", channel_name),
                        ("store_id", "=", store.id),
                    ],
                    limit=1,
                )
            )
            missing_products = self._shoppingfeed_validate_products(order)
            if missing_products:
                error_msg = f"Products not found: {', '.join(missing_products)}"
                self._create_shoppingfeed_log(store, order, sf_channel, error_msg)
                continue
            try:
                with self.env.cr.savepoint():
                    billing = order.get("billingAddress", {}) or {}
                    additional_fields = order.get("additionalFields", {}) or {}
                    partner = self._shoppingfeed_prepare_partner(
                        billing, store, sf_channel, additional_fields
                    )
                    shipping_partner = self._shoppingfeed_prepare_shipping(
                        order.get("shippingAddress", {}), partner, store
                    )
                    # Type mapping
                    mapping = store.marketplace_customer_group_ids.filtered(
                        lambda m,
                        channel_name=channel_name: m.channel_id.sf_channel_name
                        == channel_name
                    )
                    order_type_id = mapping.order_type_id.id if mapping else False
                    # Carrier mapping
                    shipment = order.get("shipment", {}) or {}
                    carrier_name = shipment.get("carrier")
                    shipping_country = (
                        shipping_partner.country_id if shipping_partner else None
                    )
                    carrier = self._shoppingfeed_get_carrier(
                        store, sf_channel, carrier_name, shipping_country
                    )
                    self._shoppingfeed_create_sale_order(
                        store,
                        order,
                        partner,
                        shipping_partner,
                        sf_channel,
                        order_type_id,
                        carrier,
                    )
                    self._shoppingfeed_acknowledge_order(store, order)
            except Exception as e:
                error_msg = f"Error creating order: {str(e)}"
                self._create_shoppingfeed_log(store, order, sf_channel, error_msg)
                continue


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.depends("order_id.shoppingfeed_channel_id")
    def _compute_invoice_status(self):
        res = super()._compute_invoice_status()
        self.filtered(
            lambda sol: sol.order_id._is_shoppingfeed_disable_invoicing()
        ).invoice_status = "no"
        return res
