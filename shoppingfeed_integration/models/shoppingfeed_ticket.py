# Copyright 2025 Juan Carlos Oñate - Tecnativa <juancarlos.onate@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import requests

from odoo import api, fields, models


class ShoppingfeedTicket(models.Model):
    _name = "shoppingfeed.ticket"
    _description = "Shoppingfeed Ticket"
    _order = "create_date desc"

    name = fields.Char(required=True, index=True)
    store_id = fields.Many2one("shoppingfeed.store", required=True, ondelete="cascade")
    order_id = fields.Many2one("sale.order")
    shoppingfeed_reference = fields.Char(
        help="Marketplace order reference (e.g., TEST-68fb749e8cd95).",
        copy=False,
        index=True,
        readonly=True,
    )
    ticket_type = fields.Char()
    state = fields.Selection(
        [
            ("scheduled", "Scheduled"),
            ("running", "Running"),
            ("succeed", "Succeeded"),
            ("failed", "Failed"),
            ("canceled", "Canceled"),
        ],
        default="scheduled",
    )
    message = fields.Text()
    result_data = fields.Text()
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="store_id.company_id",
        store=True,
        readonly=True,
    )
    link = fields.Char()

    @api.model
    def cron_fetch_all_tickets(self):
        # Get all active Shoppingfeed stores with valid credentials
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
            url = f"https://api.shopping-feed.com/v1/store/{store.catalog_id}/ticket"
            headers = {
                "Authorization": store.access_token,
                "Content-Type": "application/json",
            }
            response = requests.get(url, headers=headers, timeout=60)
            if response.status_code != 200:
                continue
            data = response.json() or {}
            tickets = data.get("_embedded", {}).get("ticket", [])
            for t in tickets:
                payload = t.get("payload", {}) or {}
                reference = payload.get("reference")
                order = (
                    self.env["sale.order"]
                    .sudo()
                    .search(
                        [
                            ("shoppingfeed_reference", "=", reference),
                            ("company_id", "=", store.company_id.id),
                        ],
                        limit=1,
                    )
                )
                existing = self.search(
                    [
                        ("name", "=", t.get("id")),
                        ("store_id", "=", store.id),
                    ],
                    limit=1,
                )
                vals = {
                    "store_id": store.id,
                    "order_id": order.id if order else False,
                    "shoppingfeed_reference": reference,
                    "ticket_type": t.get("type"),
                    "state": t.get("state"),
                    "message": t.get("result", {}).get("message"),
                    "result_data": str(t.get("result", {}).get("data")),
                    "link": t.get("_links", {}).get("self", {}).get("href", ""),
                }
                if existing:
                    existing.write(vals)
                else:
                    vals["name"] = t.get("id")
                    self.create(vals)
