# Copyright 2026 Tecnativa - Sergio Teruel
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import base64
from io import BytesIO

import PIL.WebPImagePlugin  # noqa: F401
from PIL import Image

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestCatalogImages(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create({"name": "SF Image Product"})
        # /shoppingfeed/image grants public access the same way the website
        # does (ir_binary._find_record_check_access): only published
        # products are readable by the anonymous user url_open() runs as.
        cls.product.product_tmpl_id.website_published = True
        cls.webp_bytes = cls._make_image_bytes("WEBP")
        cls.jpeg_bytes = cls._make_image_bytes("JPEG", color=(10, 20, 30))

    def setUp(self):
        super().setUp()
        # Pins the HTTP session to this test's database - without it,
        # url_open() can't resolve which DB to route to on a multi-db
        # instance and every request 404s before reaching the controller.
        self.authenticate(None, None)

    @staticmethod
    def _make_image_bytes(fmt, color=(200, 50, 50)):
        buffer = BytesIO()
        Image.new("RGB", (2, 2), color).save(buffer, format=fmt)
        return buffer.getvalue()

    @classmethod
    def _add_jpeg_sibling(cls, field_attachment):
        # Reproduces the RPC ImageField.onFileUploaded() / X2ManyMediaViewer.
        # onImageSave() issue after saving a webp image: a JPEG copy stored
        # as a child ir.attachment "for use in PDF files".
        return cls.env["ir.attachment"].create_unique(
            [
                {
                    "name": "image.jpg",
                    "description": "format: jpeg",
                    "datas": base64.b64encode(cls.jpeg_bytes),
                    "res_id": field_attachment.id,
                    "res_model": "ir.attachment",
                    "mimetype": "image/jpeg",
                }
            ]
        )

    def test_product_webp_image_reuses_precomputed_jpeg_sibling(self):
        # product.product's image_1920 is a compute/inverse field: for a
        # single-variant product (the common case) it routes the write to
        # the template's image_1920, not to an attachment of its own.
        self.product.image_1920 = base64.b64encode(self.webp_bytes)
        field_attachment = self.env["ir.attachment"].search(
            [
                ("res_model", "=", "product.template"),
                ("res_field", "=", "image_1920"),
                ("res_id", "=", self.product.product_tmpl_id.id),
            ],
            limit=1,
        )
        self.assertTrue(field_attachment)
        self._add_jpeg_sibling(field_attachment)

        response = self.url_open(
            f"/shoppingfeed/image/product.product/{self.product.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "image/jpeg")
        # Exact byte match proves the pre-existing sibling was served as-is
        # instead of being re-encoded through PIL.
        self.assertEqual(response.content, self.jpeg_bytes)

    def test_product_image_webp_reuses_precomputed_jpeg_sibling(self):
        product_image = self.env["product.image"].create(
            {
                "name": "Gallery image",
                "product_tmpl_id": self.product.product_tmpl_id.id,
                "image_1920": base64.b64encode(self.webp_bytes),
            }
        )
        field_attachment = self.env["ir.attachment"].search(
            [
                ("res_model", "=", "product.image"),
                ("res_field", "=", "image_1920"),
                ("res_id", "=", product_image.id),
            ],
            limit=1,
        )
        self.assertTrue(field_attachment)
        self._add_jpeg_sibling(field_attachment)

        response = self.url_open(
            f"/shoppingfeed/image/product.image/{product_image.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "image/jpeg")
        self.assertEqual(response.content, self.jpeg_bytes)

    def test_webp_image_without_sibling_falls_back_to_on_the_fly_conversion(self):
        self.product.image_1920 = base64.b64encode(self.webp_bytes)
        response = self.url_open(
            f"/shoppingfeed/image/product.product/{self.product.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "image/jpeg")
        self.assertNotEqual(response.content, self.webp_bytes)
        self.assertEqual(Image.open(BytesIO(response.content)).format, "JPEG")

    def test_disallowed_model_returns_404(self):
        response = self.url_open(
            f"/shoppingfeed/image/res.partner/{self.env.user.partner_id.id}"
        )
        self.assertEqual(response.status_code, 404)
