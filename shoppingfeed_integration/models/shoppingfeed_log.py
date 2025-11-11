# Copyright 2025 Juan Carlos Oñate - Tecnativa <juancarlos.onate@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class ShoppingfeedLog(models.Model):
    _name = "shoppingfeed.log"
    _description = "Shoppingfeed Order Import Log"
    _order = "create_date desc"

    name = fields.Char(required=True, index=True)
    store_id = fields.Many2one(
        comodel_name="shoppingfeed.store",
        string="Store",
        ondelete="cascade",
        index=True,
    )
    channel_id = fields.Many2one(
        comodel_name="shoppingfeed.channel",
        string="Channel",
        ondelete="set null",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="store_id.company_id",
        store=True,
        readonly=True,
    )
    shoppingfeed_reference = fields.Char(index=True)
    error_message = fields.Text()
