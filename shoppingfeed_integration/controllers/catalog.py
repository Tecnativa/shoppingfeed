# Copyright 2025 Juan Carlos Oñate - Tecnativa <juancarlos.onate@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import tempfile
from datetime import datetime

from lxml import etree

from odoo import http, release
from odoo.http import Response, request


class CatalogController(http.Controller):
    @http.route(
        ["/catalog.xml", "/catalog/<string:catalog_id>.xml"],
        type="http",
        auth="public",
        website=True,
        csrf=False,
    )
    def catalog_feed(self, catalog_id=None, **kwargs):
        # Generate Shoppingfeed product catalog XML for a specific store.
        if not catalog_id:
            return Response(
                "<error>Missing required catalog_id.</error>",
                status=400,
                content_type="application/xml;charset=utf-8",
            )
        store = (
            request.env["shoppingfeed.store"]
            .sudo()
            .search([("catalog_id", "=", catalog_id)], limit=1)
        )
        if not store:
            return Response(
                f"<error>Store with catalog_id {catalog_id} not found.</error>",
                status=404,
                content_type="application/xml;charset=utf-8",
            )
        catalog_file = self._generate_catalog_file(store)
        return Response(
            catalog_file,
            content_type="application/xml;charset=utf-8",
            status=200,
            direct_passthrough=True,
        )

    def _get_product_domain_for_store(self, store):
        domain = []
        if store.export_only_selected:
            domain.append(("export_to_shoppingfeed", "=", True))
        domain.append(("shoppingfeed_store_ids", "in", store.id))
        # Product type filters
        product_types = []
        if store.export_type_goods:
            product_types.append("consu")
        if store.export_type_service:
            product_types.append("service")
        if store.export_type_combo:
            product_types.append("combo")
        domain.append(("type", "in", product_types))
        if not store.export_out_of_stock:
            domain.append(("qty_available", ">", 0))
        if not store.export_disabled_products:
            domain.append(("active", "=", True))
        if not store.export_not_salable_products:
            domain.append(("sale_ok", "=", True))
        if store.allowed_categ_ids:
            domain.append(("public_categ_ids", "in", store.allowed_categ_ids.ids))
        return domain

    def _get_product_env_for_store(self, store):
        env = request.env["product.product"].sudo().with_company(store.company_id)
        if store.lang_id:
            env = env.with_context(lang=store.lang_id.code)
        return env

    def _get_products_for_store(self, store):
        return self._get_product_env_for_store(store).search(
            self._get_product_domain_for_store(store)
        )

    def _generate_catalog_file(self, store):
        catalog_file = tempfile.TemporaryFile()
        for chunk in self._iter_catalog_xml(store):
            catalog_file.write(chunk)
        catalog_file.seek(0)
        return catalog_file

    def _iter_catalog_xml(self, store, batch_size=500):
        product_env = self._get_product_env_for_store(store)
        domain = self._get_product_domain_for_store(store)
        product_ids = product_env.search(domain).ids
        total_products = len(product_ids)
        generation_started_at = datetime.now()
        catalog_context = self._get_catalog_context(store)

        yield b'<?xml version="1.0" encoding="UTF-8"?>\n'
        yield b'<catalog>\n<products version="1.0.0">\n'
        for index in range(0, total_products, batch_size):
            batch = product_env.browse(product_ids[index : index + batch_size])
            self._fetch_product_batch_fields(store, batch)
            batch_context = self._get_product_batch_context(store, batch)
            for product in batch:
                product_el = self._build_product_xml(
                    store, product, catalog_context, batch_context
                )
                yield etree.tostring(product_el, encoding="UTF-8")
                yield b"\n"
            request.env.cache.invalidate()
        yield b"</products>\n"
        metadata_el = self._build_metadata_xml(total_products, generation_started_at)
        yield etree.tostring(metadata_el, encoding="UTF-8")
        yield b"\n</catalog>\n"

    def _get_catalog_context(self, store):
        return {
            "allowed_categ_ids": set(store.allowed_categ_ids.ids),
            "base_url": store.get_base_url().rstrip("/"),
        }

    def _fetch_product_batch_fields(self, store, products):
        field_names = [
            "barcode",
            "default_code",
            "description_sale",
            "lst_price",
            "name",
            "product_brand_id",
            "product_template_attribute_value_ids",
            "product_template_image_ids",
            "product_tmpl_id",
            "public_categ_ids",
            "sale_ok",
            "sf_forced_category_id",
            "taxes_id",
            "type",
            "website_description",
            "website_url",
            "weight",
        ]
        if store.custom_sku_field_id:
            field_names.append(store.custom_sku_field_id.name)
        field_names.extend(
            attr_field.field_id.name
            for attr_field in store.additional_attribute_field_ids
        )
        products.fetch(set(field_names))

    def _get_product_batch_context(self, store, products):
        base_prices = self._get_base_prices(store, products)
        quantity_values = self._get_quantity_values(store, products)
        main_images = self._get_main_images(products)
        additional_prices = {}
        for pricelist in store.additional_pricelist_ids:
            if not pricelist.shoppingfeed_attribute_name:
                continue
            prices = pricelist._get_products_price(products, 1.0, None)
            additional_prices[pricelist.id] = {
                product_id: pricelist.currency_id.round(price)
                for product_id, price in prices.items()
            }
        return {
            "additional_prices": additional_prices,
            "base_prices": base_prices,
            "main_images": main_images,
            "quantity_values": quantity_values,
        }

    def _get_base_prices(self, store, products):
        currency = (
            store.pricelist_id.currency_id
            if store.pricelist_id
            else store.company_id.currency_id
        )
        if store.pricelist_id:
            prices = store.pricelist_id._get_products_price(products, 1.0, None)
        else:
            prices = {product.id: product.lst_price or 0.0 for product in products}
        return {
            product_id: currency.round(price) for product_id, price in prices.items()
        }

    def _get_quantity_values(self, store, products):
        if not store.use_actual_stock_state:
            return {}
        if store.quantity_type == "virtual":
            return {
                data["id"]: data["virtual_available"]
                for data in products.read(["virtual_available"])
            }
        return dict(products._get_only_qty_available())

    def _get_main_images(self, products):
        products_data = products.with_context(bin_size=True).read(
            ["image_variant_1920", "product_tmpl_id"]
        )
        template_ids = {
            data["product_tmpl_id"][0]
            for data in products_data
            if data["product_tmpl_id"] and not data["image_variant_1920"]
        }
        template_images = {
            data["id"]: bool(data["image_1920"])
            for data in products.env["product.template"]
            .browse(template_ids)
            .with_context(bin_size=True)
            .read(["image_1920"])
        }
        return {
            data["id"]: bool(data["image_variant_1920"])
            or template_images.get(data["product_tmpl_id"][0], False)
            for data in products_data
        }

    def _build_catalog_xml(self, store, products, base_url):
        catalog_el = etree.Element("catalog")
        products_el = etree.SubElement(catalog_el, "products", version="1.0.0")
        catalog_context = self._get_catalog_context(store)
        if base_url:
            catalog_context["base_url"] = base_url.rstrip("/")
        batch_context = self._get_product_batch_context(store, products)
        for product in products:
            products_el.append(
                self._build_product_xml(store, product, catalog_context, batch_context)
            )
        self._add_metadata(catalog_el, len(products))
        return catalog_el

    def _build_product_xml(self, store, product, catalog_context, batch_context):
        product_el = etree.Element("product")
        self._add_product_base_info(store, product_el, product, catalog_context)
        self._add_product_price(store, product_el, product, batch_context)
        self._add_product_stock(store, product_el, product, batch_context)
        self._add_product_media(
            store, product_el, product, catalog_context, batch_context
        )
        self._add_product_attributes(store, product_el, product, batch_context)
        return product_el

    def _get_base_price(self, store, product, batch_context=None):
        if batch_context:
            price = batch_context["base_prices"].get(product.id, 0.0)
        else:
            price = product.lst_price or 0.0
            if store.pricelist_id:
                price = store.pricelist_id._get_product_price(product, 1.0, None)
        currency = (
            store.pricelist_id.currency_id
            if store.pricelist_id
            else store.company_id.currency_id
        )
        return currency.round(price)

    def _add_product_base_info(self, store, product_el, product, catalog_context):
        base_url = catalog_context["base_url"]
        if store.use_product_id_as_sku:
            sku_value = str(product.id)
        elif store.custom_sku_field_id:
            sku_value = getattr(product, store.custom_sku_field_id.name, False) or str(
                product.id
            )
        else:
            sku_value = product.default_code or str(product.id)
        etree.SubElement(
            product_el, "reference"
        ).text = f"{sku_value}_{store.country_id.code}"
        etree.SubElement(product_el, "gtin").text = product.barcode or ""
        etree.SubElement(product_el, "name").text = etree.CDATA(product.name or "")
        if product.website_url:
            product_url = base_url + product.website_url
            etree.SubElement(product_el, "link").text = etree.CDATA(product_url)
        if product.weight:
            etree.SubElement(product_el, "weight").text = str(product.weight)
        if product.product_brand_id:
            brand_el = etree.SubElement(product_el, "brand")
            etree.SubElement(brand_el, "name").text = etree.CDATA(
                product.product_brand_id.name or ""
            )
        if product.sf_forced_category_id:
            category = product.sf_forced_category_id
        else:
            category = product.public_categ_ids.filtered(
                lambda categ: categ.id in catalog_context["allowed_categ_ids"]
            )[:1]
        if category:
            category_el = etree.SubElement(product_el, "category")
            etree.SubElement(category_el, "name").text = etree.CDATA(
                category.display_name.replace(" / ", " > ")
            )
            etree.SubElement(category_el, "link").text = etree.CDATA(
                f"{base_url}/shop/category/{category.id}"
            )
        description_el = etree.SubElement(product_el, "description")
        full_desc = product.website_description or ""
        etree.SubElement(description_el, "full").text = etree.CDATA(full_desc)
        short_desc = product.description_sale or ""
        etree.SubElement(description_el, "short").text = etree.CDATA(short_desc)

    def _add_product_price(self, store, product_el, product, batch_context=None):
        price = self._get_base_price(store, product, batch_context)
        if store.include_taxes_in_price and product.taxes_id:
            currency = (
                store.pricelist_id.currency_id
                if store.pricelist_id
                else store.company_id.currency_id
            )
            product_taxes = product.taxes_id._filter_taxes_by_company(store.company_id)
            tax_result = product_taxes.compute_all(
                price, currency=currency, quantity=1.0, product=product
            )
            price = currency.round(tax_result["total_included"])
        etree.SubElement(product_el, "price").text = str(price)

    def _get_quantity_value(self, store, product, batch_context=None):
        if batch_context:
            return batch_context["quantity_values"].get(product.id, 0.0)
        if store.quantity_type == "virtual":
            return product.virtual_available
        return product.qty_available

    def _add_product_stock(self, store, product_el, product, batch_context=None):
        if not store.use_actual_stock_state:
            quantity_value = store.default_quantity
        else:
            quantity_value = (
                self._get_quantity_value(store, product, batch_context) or 0
            )
            if product.type == "service":
                quantity_value = store.default_quantity
        if not product.sale_ok and store.force_zero_quantity_non_salable:
            quantity_value = 0
        etree.SubElement(product_el, "quantity").text = str(int(quantity_value))

    def _add_product_media(
        self, store, product_el, product, catalog_context, batch_context=None
    ):
        base_url = catalog_context["base_url"]
        images_el = etree.SubElement(product_el, "images")
        product_images = product.product_template_image_ids
        if store.export_all_images:
            all_images = product_images
        else:
            all_images = product_images[: store.exported_image_count]
        if self._has_main_image(product, batch_context):
            etree.SubElement(images_el, "image", type="main").text = etree.CDATA(
                f"{base_url}/web/image/product.product/{product.id}/image_1920"
            )
        for img in all_images:
            etree.SubElement(images_el, "image").text = etree.CDATA(
                f"{base_url}/web/image/{img._name}/{img.id}/image_1920"
            )

    def _has_main_image(self, product, batch_context=None):
        if batch_context:
            return batch_context["main_images"].get(product.id, False)
        return self._get_main_images(product).get(product.id, False)

    def _add_product_attributes(self, store, product_el, product, batch_context=None):
        attributes_el = etree.SubElement(product_el, "attributes")
        # Attributes that generate variants
        for value in product.product_template_attribute_value_ids:
            # Skip if attribute is not marked for export to Shoppingfeed
            if not value.attribute_id.shoppingfeed_export:
                continue
            attr_el = etree.SubElement(attributes_el, "attribute")
            name = (
                value.attribute_id.shoppingfeed_code_name_attribute
                or value.attribute_id.name
            )
            etree.SubElement(attr_el, "name").text = name
            etree.SubElement(attr_el, "value").text = value.name
        # Attributes that do NOT generate variants
        for line in product.product_tmpl_id.attribute_line_ids.filtered(
            lambda line_var: (
                line_var.attribute_id.create_variant == "no_variant"
                and line_var.attribute_id.shoppingfeed_export
            )
        ):
            if line.value_ids:
                values = ", ".join(line.value_ids.mapped("name"))
                attr_el = etree.SubElement(attributes_el, "attribute")
                name = (
                    line.attribute_id.shoppingfeed_code_name_attribute
                    or line.attribute_id.name
                )
                etree.SubElement(attr_el, "name").text = name
                etree.SubElement(attr_el, "value").text = values
        if store.additional_attribute_field_ids:
            for attr_field in store.additional_attribute_field_ids:
                field = attr_field.field_id
                value = getattr(product, field.name, False)
                if not value:
                    continue
                attr_el = etree.SubElement(attributes_el, "attribute")
                attr_name = (
                    attr_field.custom_name or field.field_description or field.name
                )
                etree.SubElement(attr_el, "name").text = attr_name
                if field.ttype == "many2one":
                    etree.SubElement(attr_el, "value").text = (
                        value.display_name
                        if hasattr(value, "display_name")
                        else str(value.id)
                    )
                elif field.ttype == "boolean":
                    etree.SubElement(attr_el, "value").text = (
                        "True" if value else "False"
                    )
                elif field.ttype == "html":
                    etree.SubElement(attr_el, "value").text = etree.CDATA(str(value))
                elif field.ttype == "datetime":
                    etree.SubElement(attr_el, "value").text = etree.CDATA(str(value))
                else:
                    etree.SubElement(attr_el, "value").text = str(value)
        self._add_product_price_attributes(store, attributes_el, product, batch_context)

    def _add_product_price_attributes(
        self, store, attributes_el, product, batch_context=None
    ):
        # Export price without taxes as additional attribute for marketplaces
        if store.export_price_without_tax and store.price_without_tax_attribute_name:
            price_without_tax = self._get_base_price(store, product, batch_context)
            attr_el = etree.SubElement(attributes_el, "attribute")
            etree.SubElement(
                attr_el, "name"
            ).text = store.price_without_tax_attribute_name
            etree.SubElement(attr_el, "value").text = str(price_without_tax)
        # Additional pricelists as price attributes
        if store.additional_pricelist_ids:
            for pricelist in store.additional_pricelist_ids:
                if not pricelist.shoppingfeed_attribute_name:
                    continue
                if batch_context:
                    price = batch_context["additional_prices"][pricelist.id].get(
                        product.id, 0.0
                    )
                else:
                    price = pricelist.currency_id.round(
                        pricelist._get_product_price(product, 1.0, None)
                    )
                attr_el = etree.SubElement(attributes_el, "attribute")
                etree.SubElement(
                    attr_el, "name"
                ).text = pricelist.shoppingfeed_attribute_name
                etree.SubElement(attr_el, "value").text = str(price)

    def _build_metadata_xml(self, total_products, started_at):
        metadata_el = etree.Element("metadata")
        self._add_metadata_values(metadata_el, total_products, started_at)
        return metadata_el

    def _add_metadata(self, catalog_el, total_products):
        metadata_el = etree.SubElement(catalog_el, "metadata")
        self._add_metadata_values(metadata_el, total_products, datetime.now())

    def _add_metadata_values(self, metadata_el, total_products, started_at):
        etree.SubElement(metadata_el, "platform").text = f"Odoo:{release.version}"
        etree.SubElement(
            metadata_el, "agent"
        ).text = f"shoppingfeed_integration:{release.version}"
        etree.SubElement(metadata_el, "startedAt").text = started_at.isoformat()
        etree.SubElement(metadata_el, "finishedAt").text = datetime.now().isoformat()
        etree.SubElement(metadata_el, "invalid").text = "0"
        etree.SubElement(metadata_el, "ignored").text = "0"
        etree.SubElement(metadata_el, "written").text = str(total_products)
