# Copyright 2025 Juan Carlos Oñate - Tecnativa <juancarlos.onate@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class ShoppingfeedChannelCountryCarrier(models.Model):
    _name = "shoppingfeed.channel.country.carrier"
    _description = "Shoppingfeed Channel Carrier by Country"

    channel_id = fields.Many2one(
        comodel_name="shoppingfeed.channel",
        required=True,
        ondelete="cascade",
    )
    country_id = fields.Many2one(
        comodel_name="res.country",
        string="Delivery Country",
        required=True,
    )
    delivery_carrier_id = fields.Many2one(
        comodel_name="delivery.carrier",
        string="Carrier",
        required=True,
    )
