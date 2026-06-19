# Copyright 2025 Juan Carlos Oñate - Tecnativa <juancarlos.onate@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import io
import json
import logging

import requests

from odoo import _, models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def _shoppingfeed_upload_invoice(self):
        for move in self:
            if move.move_type != "out_invoice":
                continue
            sale_orders = move.line_ids.sale_line_ids.order_id.filtered(
                lambda so, move=move: so.company_id == move.company_id
            )
            sale_order = sale_orders[:1]
            if (
                not sale_order
                or not sale_order.shoppingfeed_order_ref
                or not sale_order.shoppingfeed_store_id
                or not sale_order.shoppingfeed_channel_id
                or sale_order.shoppingfeed_channel_id.upload_invoice_not_allowed
            ):
                continue
            store = sale_order.shoppingfeed_store_id
            if not store.access_token or not store.catalog_id:
                continue
            if store._shoppingfeed_is_demo_mode():
                continue
            pdf_content, __ = self.env["ir.actions.report"]._render_qweb_pdf(
                "account.account_invoices", move.ids
            )
            pdf_file = io.BytesIO(pdf_content)
            pdf_file.name = f"{move.name or 'invoice'}.pdf"
            url = f"https://api.shopping-feed.com/v1/store/{store.catalog_id}/order/upload-documents"
            headers = {
                "Authorization": store.access_token,
            }
            payload = {
                "order": [
                    {
                        "id": int(sale_order.shoppingfeed_order_ref),
                        "documents": [{"type": "invoice"}],
                    }
                ]
            }
            files = {"files[]": (pdf_file.name, pdf_file, "application/pdf")}
            data = {"body": json.dumps(payload)}
            response = requests.post(
                url, headers=headers, files=files, data=data, timeout=30
            )
            if response.ok:
                move.message_post(
                    body=_(
                        "Invoice uploaded to Shoppingfeed successfully "
                        "(order ref: %(ref)s, HTTP %(status)s).",
                        ref=sale_order.shoppingfeed_order_ref,
                        status=response.status_code,
                    ),
                    subtype_xmlid="mail.mt_note",
                )
            else:
                move.message_post(
                    body=_(
                        "Failed to upload invoice to Shoppingfeed "
                        "(order ref: %(ref)s, HTTP %(status)s): %(detail)s",
                        ref=sale_order.shoppingfeed_order_ref,
                        status=response.status_code,
                        detail=response.text,
                    ),
                    subtype_xmlid="mail.mt_note",
                )

    def _shoppingfeed_auto_pay(self):
        for move in self:
            if (
                move.move_type not in ("out_invoice", "out_refund")
                or move.payment_state == "paid"
            ):
                continue
            sale_orders = move.line_ids.sale_line_ids.order_id.filtered(
                lambda so, move=move: so.company_id == move.company_id
            )
            sale_order = sale_orders[:1]
            channel = sale_order.shoppingfeed_channel_id
            if not sale_order or not channel or not channel.auto_pay:
                continue
            if move.move_type == "out_refund":
                # Force the outbound mirror line: the computed preferred for a
                # sale document is the partner inbound line, invalid here.
                method_line = channel._shoppingfeed_get_refund_payment_method_line()
                if not method_line:
                    continue
                move.preferred_payment_method_line_id = method_line
            else:
                if (
                    not move.preferred_payment_method_line_id
                    and channel.payment_method_line_id
                ):
                    move.preferred_payment_method_line_id = (
                        channel.payment_method_line_id
                    )
                if not move.preferred_payment_method_line_id:
                    continue
            self.env["account.payment.register"].with_context(
                active_model="account.move",
                active_ids=move.ids,
            ).create({})._create_payments()

    def _post(self, soft=True):
        posted = super()._post(soft)
        invoices = posted.filtered(lambda move: move.is_invoice())
        invoices._shoppingfeed_upload_invoice()
        invoices._shoppingfeed_auto_pay()
        return posted
