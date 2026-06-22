# Copyright 2025 Juan Carlos Oñate - Tecnativa <juancarlos.onate@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import logging

import requests

from odoo import fields, models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    shoppingfeed_shipped = fields.Boolean(
        copy=False,
        help="Indicates if this picking has already been sent to ShoppingFeed",
    )

    def _action_done(self):
        res = super()._action_done()
        self._shoppingfeed_notify_shipment()
        return res

    def _shoppingfeed_tracking_number(self):
        self.ensure_one()
        return self.carrier_tracking_ref or ""

    def _shoppingfeed_ship_order_payload(self, sale_order):
        self.ensure_one()
        return {
            "id": int(sale_order.shoppingfeed_order_ref),
            "carrier": self.carrier_id.name or "Unknown",
            "trackingLink": self.carrier_tracking_url or "",
            "trackingNumber": self._shoppingfeed_tracking_number(),
        }

    def _shoppingfeed_notify_shipment(self):
        # Notify Shoppingfeed that the order has been shipped
        for picking in self:
            _logger.info("Envio de tracking a SF")
            sale_order = picking.sale_id
            if (
                picking.shoppingfeed_shipped
                or not sale_order
                or not sale_order.shoppingfeed_order_ref
                or not sale_order.shoppingfeed_store_id
            ):
                _logger.info("Envio de tracking a SF 1er - contune")
                continue
            store = sale_order.shoppingfeed_store_id
            if (
                not store.access_token
                or not store.catalog_id
                or not store.notify_shipment
            ):
                _logger.info("Envio de tracking a SF 2 - contune")
                continue
            if store._shoppingfeed_is_demo_mode():
                continue
            order_payload = picking._shoppingfeed_ship_order_payload(sale_order)
            if not order_payload:
                _logger.info("Envio de tracking a SF 4 - contune")
                continue
            url = (
                f"https://api.shopping-feed.com/v1/store/{store.catalog_id}/order/ship"
            )
            headers = {
                "Authorization": store.access_token,
                "Content-Type": "application/json",
            }
            payload = {"order": [order_payload]}
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            _logger.info(
                f"Envio de tracking a SF after "
                f"response status: {response.status_code} "
                f"response text: {response.text}"
            )
            if response.status_code == 202:
                picking.shoppingfeed_shipped = True
