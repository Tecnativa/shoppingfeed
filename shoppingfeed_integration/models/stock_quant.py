# Copyright 2025 Juan Carlos Oñate - Tecnativa <juancarlos.onate@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import requests

from odoo import models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    def write(self, vals):
        res = super().write(vals)
        if "quantity" in vals or "inventory_quantity" in vals:
            self._shoppingfeed_update_inventory()
        return res

    def _shoppingfeed_update_inventory(self):
        for quant in self:
            product = quant.product_id
            if not product.default_code or not product.shoppingfeed_store_ids:
                continue
            stores = product.shoppingfeed_store_ids.filtered(
                lambda store, product=product, quant=quant: (
                    not store.export_only_selected or product.export_to_shoppingfeed
                )
                and store.update_quantities_realtime
                and store.company_id == quant.company_id
            )
            quantity = int(product.qty_available)
            for store in stores:
                if store._shoppingfeed_is_demo_mode():
                    continue
                reference = f"{product.default_code}_{store.country_id.code}"
                payload = {
                    "inventory": [{"reference": reference, "quantity": quantity}]
                }
                url = f"https://api.shopping-feed.com/v1/catalog/{store.catalog_id}/inventory"
                headers = {
                    "Authorization": store.access_token,
                    "Content-Type": "application/json",
                }
                requests.put(url, headers=headers, json=payload, timeout=60)
