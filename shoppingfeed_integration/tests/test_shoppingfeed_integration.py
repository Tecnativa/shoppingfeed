# Copyright 2026 Juan Carlos Oñate - Tecnativa <juancarlos.onate@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestShoppingfeedIntegration(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.inbound_payment_method_line = cls.env["account.payment.method.line"].create(
            {
                "name": "SF Inbound Payment Method",
                "payment_method_id": cls.bank_journal.available_payment_method_ids[
                    0
                ].id,
                "payment_type": "inbound",
                "journal_id": cls.bank_journal.id,
            }
        )
        cls.sf_store = cls.env["shoppingfeed.store"].create(
            {
                "name": "Test SF Store",
                "username": "test_user",
                "password": "test_pass",
                "company_id": cls.env.company.id,
            }
        )
        cls.sf_channel = cls.env["shoppingfeed.channel"].create(
            {
                "name": "Test Channel",
                "store_id": cls.sf_store.id,
                "payment_method_line_id": cls.inbound_payment_method_line.id,
                "auto_pay": True,
            }
        )
        cls.product_a.default_code = "TEST-SKU-001"

    @classmethod
    def _sf_order_line(cls, product=None):
        product = product or cls.product_a
        return Command.create(
            {
                "product_id": product.id,
                "product_uom_qty": 1.0,
                "price_unit": product.list_price,
            }
        )

    def test_partner_gets_payment_method_on_create(self):
        """New partner created during SF import receives
        property_inbound_payment_method_line_id from the channel."""
        billing = {
            "email": "sf_new_customer@example.com",
            "firstName": "SF",
            "lastName": "Customer",
            "street": "Calle Test 1",
            "postalCode": "28001",
            "city": "Madrid",
            "country": "ES",
            "phone": "600000000",
        }
        partner = self.env["sale.order"]._shoppingfeed_prepare_partner(
            billing, self.sf_store, channel=self.sf_channel
        )
        self.assertRecordValues(
            partner,
            [
                {
                    "property_inbound_payment_method_line_id": (
                        self.inbound_payment_method_line.id
                    )
                }
            ],
        )

    def test_invoice_auto_paid_on_post(self):
        """Invoice from a SF order with auto_pay=True is paid on confirmation."""
        self.partner_a.property_inbound_payment_method_line_id = (
            self.inbound_payment_method_line
        )
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_a.id,
                "shoppingfeed_order_ref": "SF-TEST-AUTOPAY-001",
                "shoppingfeed_store_id": self.sf_store.id,
                "shoppingfeed_channel_id": self.sf_channel.id,
                "order_line": [self._sf_order_line()],
            }
        )
        sale_order.action_confirm()
        invoice = sale_order._create_invoices()
        invoice.action_post()
        self.assertEqual(invoice.payment_state, "paid")

    def test_invoice_not_auto_paid_when_disabled(self):
        """Invoice is NOT auto-paid when channel has auto_pay=False."""
        self.sf_channel.auto_pay = False
        self.partner_a.property_inbound_payment_method_line_id = (
            self.inbound_payment_method_line
        )
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_a.id,
                "shoppingfeed_order_ref": "SF-TEST-NOPAY-001",
                "shoppingfeed_store_id": self.sf_store.id,
                "shoppingfeed_channel_id": self.sf_channel.id,
                "order_line": [self._sf_order_line()],
            }
        )
        sale_order.action_confirm()
        invoice = sale_order._create_invoices()
        invoice.action_post()
        self.assertNotEqual(invoice.payment_state, "paid")
        self.sf_channel.auto_pay = True

    def test_product_reference_cleaning(self):
        """_shoppingfeed_clean_product_reference strips 2-char country suffixes only."""
        so = self.env["sale.order"]
        self.assertEqual(
            so._shoppingfeed_clean_product_reference("SKU123_ES"), "SKU123"
        )
        self.assertEqual(
            so._shoppingfeed_clean_product_reference("SKU123_FR"), "SKU123"
        )
        self.assertEqual(so._shoppingfeed_clean_product_reference("SKU123"), "SKU123")
        self.assertEqual(
            so._shoppingfeed_clean_product_reference("SKU123_EUR"), "SKU123_EUR"
        )

    def test_product_reference_resolution_with_alias(self):
        """_shoppingfeed_resolve_product_reference follows alias mapping."""
        so = self.env["sale.order"]
        aliases = {"OLD-SKU": "NEW-SKU_ES"}
        self.assertEqual(
            so._shoppingfeed_resolve_product_reference("OLD-SKU", aliases), "NEW-SKU"
        )
        self.assertEqual(
            so._shoppingfeed_resolve_product_reference("DIRECT_ES", aliases), "DIRECT"
        )

    def test_validate_products_all_found(self):
        """_shoppingfeed_validate_products returns empty list when all SKUs exist."""
        order = {
            "items": [{"reference": "TEST-SKU-001"}],
            "itemsReferencesAliases": {},
        }
        self.assertEqual(
            self.env["sale.order"]._shoppingfeed_validate_products(order), []
        )

    def test_validate_products_missing_sku(self):
        """_shoppingfeed_validate_products returns missing SKUs."""
        order = {
            "items": [{"reference": "NONEXISTENT-SKU"}],
            "itemsReferencesAliases": {},
        }
        missing = self.env["sale.order"]._shoppingfeed_validate_products(order)
        self.assertIn("NONEXISTENT-SKU", missing)

    def test_create_sale_order_from_sf_data(self):
        """_shoppingfeed_create_sale_order creates a sale.order with SF metadata."""
        order_dict = {
            "id": "SF-999001",
            "reference": "MKT-TEST-REF-001",
            "status": "waiting_shipment",
            "payment": {"currency": "EUR", "shippingAmount": 0.0},
            "items": [],
            "itemsReferencesAliases": {},
            "storeId": "test",
        }
        sale_order = self.env["sale.order"]._shoppingfeed_create_sale_order(
            self.sf_store,
            order_dict,
            self.partner_a,
            None,
            self.sf_channel,
            False,
            False,
        )
        self.assertRecordValues(
            sale_order,
            [
                {
                    "shoppingfeed_order_ref": "SF-999001",
                    "shoppingfeed_reference": "MKT-TEST-REF-001",
                    "client_order_ref": "MKT-TEST-REF-001",
                    "shoppingfeed_channel_id": self.sf_channel.id,
                    "shoppingfeed_store_id": self.sf_store.id,
                    "partner_id": self.partner_a.id,
                }
            ],
        )
