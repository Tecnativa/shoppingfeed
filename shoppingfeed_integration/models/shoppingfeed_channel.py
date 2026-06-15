# Copyright 2025 Juan Carlos Oñate - Tecnativa <juancarlos.onate@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class ShoppingfeedChannel(models.Model):
    _name = "shoppingfeed.channel"
    _description = "Shoppingfeed Channel"
    _sql_constraints = [
        (
            "unique_sf_channel_name_per_store",
            "UNIQUE(sf_channel_name, store_id)",
            "API channel name must be unique per store.",
        )
    ]

    name = fields.Char(required=True)
    sf_channel_name = fields.Char(
        readonly=True,
        copy=False,
        help=(
            "Channel identifier as received from the Shoppingfeed API. "
            "Used internally to match incoming orders to this channel. "
            "Set automatically on account sync."
        ),
    )
    store_id = fields.Many2one(
        comodel_name="shoppingfeed.store",
        string="Store",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="store_id.company_id",
        store=True,
    )
    default_delivery_carrier_id = fields.Many2one(
        comodel_name="delivery.carrier",
        string="Default Delivery Carrier",
        help=(
            "Default carrier to assign to imported orders from this channel "
            "when the carrier from Shoppingfeed is not mapped. "
            "If not set, the store's default carrier will be used instead."
        ),
    )
    country_carrier_ids = fields.One2many(
        comodel_name="shoppingfeed.channel.country.carrier",
        inverse_name="channel_id",
        string="Carriers by Country",
        help=(
            "Override the default carrier based on the delivery country. "
            "If the order's destination country matches one of these rules, "
            "the specified carrier will be used instead of the channel default."
        ),
    )
    upload_invoice_not_allowed = fields.Boolean(
        help=(
            "Indicates whether this channel does NOT support invoice document upload. "
            "Based on Shoppingfeed API documentation — see: "
            "https://docs.shopping-feed.com/#order-operations-supported-per-channel"
        ),
        default=False,
    )
    disable_invoicing = fields.Boolean(
        help=(
            "Mark this field if the channel "
            "generates the invoice on your platform "
            "and it is not necessary to invoice the sales order in Odoo."
        ),
        default=False,
    )
    payment_method_line_id = fields.Many2one(
        comodel_name="account.payment.method.line",
        string="Payment Method",
        domain="""[
            ('journal_id.active', '=', True),
            ('payment_type', '=', 'inbound'),
            ('company_id', 'parent_of', company_id),
        ]""",
        help=(
            "Inbound payment method used to register the marketplace payment "
            "when an order is imported from this channel. "
            "The journal is derived from the selected payment method."
        ),
    )
    auto_pay = fields.Boolean(
        string="Automatic Payment",
        default=True,
        help=(
            "When enabled, invoices from this channel are automatically paid "
            "upon confirmation using the configured payment method."
        ),
    )
    auto_confirm_sale = fields.Boolean(
        string="Automatic Sale Confirmation",
        default=True,
        help=(
            "When enabled, sales orders from this channel are automatically confirmed."
        ),
    )
    account_id = fields.Many2one(
        comodel_name="account.account",
        string="Receivable Account",
        domain=[("account_type", "=", "asset_receivable")],
        help=(
            "Receivable account assigned to partners created from orders of this"
            " channel."
        ),
    )
    fiscal_position_id = fields.Many2one(
        "account.fiscal.position",
        string="Fiscal Position",
        check_company=True,
        ondelete="restrict",
        help="Fiscal positions are used to adapt taxes and accounts for particular "
        "customers or sales orders. The default value comes from the customer.",
    )
