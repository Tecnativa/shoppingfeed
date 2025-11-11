# Copyright 2026 Juan Carlos Oñate - Tecnativa <juancarlos.onate@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    shoppingfeed_attribute_name = fields.Char(
        help=(
            "Name to use for this pricelist when exported as an attribute "
            "in Shoppingfeed catalogs."
        ),
    )
