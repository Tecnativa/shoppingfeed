# Copyright 2025 Juan Carlos Oñate - Tecnativa <juancarlos.onate@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

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
        products = self._get_products_for_store(store)
        base_url = store.get_base_url().rstrip("/")
        catalog_el = self._build_catalog_xml(store, products, base_url)
        xml_bytes = etree.tostring(
            catalog_el, pretty_print=True, xml_declaration=True, encoding="UTF-8"
        )
        return Response(
            xml_bytes, content_type="application/xml;charset=utf-8", status=200
        )

    def _get_products_for_store(self, store):
        env = request.env["product.product"].sudo().with_company(store.company_id)
        if store.lang_id:
            env = env.with_context(lang=store.lang_id.code)
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
        return env.search(domain)

    def _build_catalog_xml(self, store, products, base_url):
        catalog_el = etree.Element("catalog")
        products_el = etree.SubElement(catalog_el, "products", version="1.0.0")
        for product in products:
            product_el = etree.SubElement(products_el, "product")
            self._add_product_base_info(store, product_el, product, base_url)
            self._add_product_price(store, product_el, product)
            self._add_product_stock(store, product_el, product)
            self._add_product_media(store, product_el, product, base_url)
            self._add_product_attributes(store, product_el, product)
        self._add_metadata(catalog_el, len(products))
        return catalog_el

    def _get_base_price(self, store, product):
        price = product.lst_price or 0.0
        if store.pricelist_id:
            price = store.pricelist_id._get_product_price(product, 1.0, None)
        currency = (
            store.pricelist_id.currency_id
            if store.pricelist_id
            else store.company_id.currency_id
        )
        return currency.round(price)

    def _add_product_base_info(self, store, product_el, product, base_url):
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
                lambda categ: categ.id in store.allowed_categ_ids.ids
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

    def _add_product_price(self, store, product_el, product):
        price = self._get_base_price(store, product)
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

    def _get_quantity_value(self, store, product):
        if store.quantity_type == "virtual":
            return product.virtual_available
        return product.qty_available

    def _add_product_stock(self, store, product_el, product):
        if not store.use_actual_stock_state:
            quantity_value = store.default_quantity
        else:
            quantity_value = self._get_quantity_value(store, product) or 0
            if product.type == "service":
                quantity_value = store.default_quantity
        if not product.sale_ok and store.force_zero_quantity_non_salable:
            quantity_value = 0
        etree.SubElement(product_el, "quantity").text = str(int(quantity_value))

    def _add_product_media(self, store, product_el, product, base_url):
        images_el = etree.SubElement(product_el, "images")
        product_images = product.product_template_image_ids
        if store.export_all_images:
            all_images = product_images
        else:
            all_images = product_images[: store.exported_image_count]
        if product.image_1920:
            etree.SubElement(images_el, "image", type="main").text = etree.CDATA(
                f"{base_url}/web/image/product.product/{product.id}/image_1920"
            )
        for img in all_images:
            etree.SubElement(images_el, "image").text = etree.CDATA(
                f"{base_url}/web/image/{img._name}/{img.id}/image_1920"
            )

    def _add_product_attributes(self, store, product_el, product):
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
            lambda line_var: line_var.attribute_id.create_variant == "no_variant"
            and line_var.attribute_id.shoppingfeed_export
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
        self._add_product_price_attributes(store, attributes_el, product)

    def _add_product_price_attributes(self, store, attributes_el, product):
        # Export price without taxes as additional attribute for marketplaces
        if store.export_price_without_tax and store.price_without_tax_attribute_name:
            price_without_tax = self._get_base_price(store, product)
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
                price = pricelist.currency_id.round(
                    pricelist._get_product_price(product, 1.0, None)
                )
                attr_el = etree.SubElement(attributes_el, "attribute")
                etree.SubElement(
                    attr_el, "name"
                ).text = pricelist.shoppingfeed_attribute_name
                etree.SubElement(attr_el, "value").text = str(price)

    def _add_metadata(self, catalog_el, total_products):
        metadata_el = etree.SubElement(catalog_el, "metadata")
        etree.SubElement(metadata_el, "platform").text = f"Odoo:{release.version}"
        etree.SubElement(
            metadata_el, "agent"
        ).text = f"shoppingfeed_integration:{release.version}"
        etree.SubElement(metadata_el, "startedAt").text = datetime.now().isoformat()
        etree.SubElement(metadata_el, "finishedAt").text = datetime.now().isoformat()
        etree.SubElement(metadata_el, "invalid").text = "0"
        etree.SubElement(metadata_el, "ignored").text = "0"
        etree.SubElement(metadata_el, "written").text = str(total_products)
