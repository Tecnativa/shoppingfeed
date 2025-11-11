# Copyright 2025 Juan Carlos Oñate - Tecnativa <juancarlos.onate@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    export_to_shoppingfeed = fields.Boolean(
        default=False,
        help="If enabled, this product will be exported to Shoppingfeed "
        "when the store is configured to export only selected products.",
    )
    shoppingfeed_store_ids = fields.Many2many(
        comodel_name="shoppingfeed.store",
        string="Shoppingfeed Stores",
        help="Select the Shoppingfeed stores where this product should be exported.",
    )
    sf_forced_category_id = fields.Many2one(
        comodel_name="product.public.category",
        string="Forced Category",
        help="If set, this category will always be used when exporting to "
        "Shoppingfeed, overriding the automatic category selection.",
    )
    sf_forced_category_parent_id = fields.Many2one(
        comodel_name="product.public.category",
        string="Forced Category Parent",
        compute="_compute_sf_forced_category_parent_id",
    )

    @api.depends("sf_forced_category_id", "sf_forced_category_id.parent_id")
    def _compute_sf_forced_category_parent_id(self):
        for rec in self:
            cat = rec.sf_forced_category_id
            rec.sf_forced_category_parent_id = cat.parent_id or cat

    def _shoppingfeed_update_pricing(self):
        # TODO: implement real-time price push to Shoppingfeed API
        pass
