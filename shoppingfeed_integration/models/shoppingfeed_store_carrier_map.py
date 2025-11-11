# Copyright 2025 Juan Carlos Oñate - Tecnativa <juancarlos.onate@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class ShoppingfeedStoreCarrierMap(models.Model):
    _name = "shoppingfeed.store.carrier.map"
    _description = "Shoppingfeed Carrier Mapping"

    store_id = fields.Many2one(
        comodel_name="shoppingfeed.store",
        ondelete="cascade",
        required=True,
    )
    carrier_name = fields.Char(
        string="Shoppingfeed Carrier Name",
        required=True,
        help="Carrier name as received from Shoppingfeed",
    )
    delivery_carrier_id = fields.Many2one(
        comodel_name="delivery.carrier",
        string="Odoo Delivery Carrier",
        required=True,
        help="Local Odoo carrier equivalent for this Shoppingfeed carrier.",
    )
