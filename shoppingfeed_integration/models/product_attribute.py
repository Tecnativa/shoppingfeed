# Copyright 2025 Juan Carlos Oñate - Tecnativa <juancarlos.onate@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class ProductAttribute(models.Model):
    _inherit = "product.attribute"

    shoppingfeed_code_name_attribute = fields.Char(
        string="Shoppingfeed Code Name",
        help="Custom attribute name used when exporting products to Shoppingfeed.",
    )
    shoppingfeed_export = fields.Boolean(
        string="Export to Shoppingfeed",
        default=True,
        help="If checked, this attribute will be included when generating the "
        "catalog for Shoppingfeed.",
    )
