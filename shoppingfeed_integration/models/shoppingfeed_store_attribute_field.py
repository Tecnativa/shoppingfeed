# Copyright 2025 Juan Carlos Oñate - Tecnativa <juancarlos.onate@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class ShoppingfeedStoreAttributeField(models.Model):
    _name = "shoppingfeed.store.attribute.field"
    _description = "Shoppingfeed Store Additional Attribute Field"
    _order = "sequence, id"

    store_id = fields.Many2one(
        comodel_name="shoppingfeed.store",
        string="Store",
        required=True,
        ondelete="cascade",
    )
    field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        string="Field",
        required=True,
        domain="[('model', '=', 'product.product'), "
        "('ttype', 'in', ['char', 'text', 'integer', 'float', "
        "'selection', 'many2one', 'boolean', 'html', 'datetime'])]",
        ondelete="cascade",
    )
    custom_name = fields.Char(
        string="Custom Attribute Name",
        help="Custom name to use in the exported catalog. "
        "If empty, the field description will be used.",
    )
    sequence = fields.Integer(default=10)
