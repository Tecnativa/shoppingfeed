# Copyright 2025 Juan Carlos Oñate - Tecnativa <juancarlos.onate@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class ShoppingfeedStoreOrderTypeMap(models.Model):
    _name = "shoppingfeed.store.order.type.map"
    _description = "Marketplace Customer Group Mapping"

    store_id = fields.Many2one(
        comodel_name="shoppingfeed.store", ondelete="cascade", required=True
    )
    channel_id = fields.Many2one(
        comodel_name="shoppingfeed.channel",
        string="Marketplace Channel",
        required=True,
        domain="[('id', 'in', parent.channel_ids)]",
    )
    order_type_id = fields.Many2one(
        comodel_name="sale.order.type",
        string="Order Type",
        required=True,
    )
