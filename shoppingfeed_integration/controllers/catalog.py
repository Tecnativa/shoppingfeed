# Copyright 2025 Juan Carlos Oñate - Tecnativa <juancarlos.onate@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import tempfile
from datetime import datetime

from lxml import etree

from odoo import http, release
from odoo.http import Response, request


class CatalogController(http.Controller):
    _PRODUCT_DATA_FIELDS = [
        "barcode",
        "default_code",
        "description_sale",
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

    _PRODUCT_FETCH_FIELDS = [
        *_PRODUCT_DATA_FIELDS,
        "lst_price",
    ]

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
        if store.export_disabled_products:
            env = env.with_context(active_test=False)
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

    def _get_product_field_names(self, store, base_fields):
        field_names = list(base_fields)
        if store.custom_sku_field_id:
            field_names.append(store.custom_sku_field_id.name)
        field_names.extend(
            attr_field.field_id.name
            for attr_field in store.additional_attribute_field_ids
        )
        return list(dict.fromkeys(field_names))

    def _fetch_product_batch_fields(self, store, products):
        products.fetch(self._get_product_field_names(store, self._PRODUCT_FETCH_FIELDS))

    def _get_product_batch_context(self, store, products):
        product_data = self._get_product_data(store, products)
        brand_names = self._get_brand_names(products, product_data)
        category_names = self._get_category_names(store, products, product_data)
        variant_attributes = self._get_variant_attributes(products, product_data)
        no_variant_attributes = self._get_no_variant_attributes(products, product_data)
        base_prices = self._get_base_prices(store, products)
        quantity_values = self._get_quantity_values(store, products)
        main_images = self._get_main_images(products, product_data)
        taxes_by_key = self._get_taxes_by_key(store, products, product_data)
        additional_prices = {}
        for pricelist in store.additional_pricelist_ids:
            if not pricelist.shoppingfeed_attribute_name:
                continue
            prices = self._get_pricelist_prices(store, pricelist, products)
            additional_prices[pricelist.id] = {
                product_id: pricelist.currency_id.round(price)
                for product_id, price in prices.items()
            }
        return {
            "additional_prices": additional_prices,
            "base_prices": base_prices,
            "brand_names": brand_names,
            "category_names": category_names,
            "main_images": main_images,
            "no_variant_attributes": no_variant_attributes,
            "product_data": product_data,
            "quantity_values": quantity_values,
            "taxes_by_key": taxes_by_key,
            "variant_attributes": variant_attributes,
        }

    def _get_product_data(self, store, products):
        return {
            data["id"]: data
            for data in products.read(
                self._get_product_field_names(store, self._PRODUCT_DATA_FIELDS)
            )
        }

    def _get_brand_names(self, products, product_data):
        brand_ids = {
            data["product_brand_id"][0]
            for data in product_data.values()
            if data["product_brand_id"]
        }
        if not brand_ids:
            return {}
        return {
            data["id"]: data["name"]
            for data in products.env["product.brand"].browse(brand_ids).read(["name"])
        }

    def _get_category_names(self, store, products, product_data):
        allowed_categ_ids = set(store.allowed_categ_ids.ids)
        category_ids = {
            category_id
            for data in product_data.values()
            for category_id in (
                [data["sf_forced_category_id"][0]]
                if data["sf_forced_category_id"]
                else [
                    public_categ_id
                    for public_categ_id in data["public_categ_ids"]
                    if public_categ_id in allowed_categ_ids
                ]
            )
        }
        if not category_ids:
            return {}
        return {
            data["id"]: data["display_name"].replace(" / ", " > ")
            for data in products.env["product.public.category"]
            .browse(category_ids)
            .read(["display_name"])
        }

    def _get_variant_attributes(self, products, product_data):
        product_ptav_ids = {
            product_id: data["product_template_attribute_value_ids"]
            for product_id, data in product_data.items()
        }
        ptav_ids = {
            ptav_id for value_ids in product_ptav_ids.values() for ptav_id in value_ids
        }
        if not ptav_ids:
            return {}
        ptav_data = (
            products.env["product.template.attribute.value"]
            .browse(ptav_ids)
            .read(["attribute_id", "name"])
        )
        attribute_ids = {
            data["attribute_id"][0] for data in ptav_data if data["attribute_id"]
        }
        attribute_data = self._get_attribute_data(products, attribute_ids)
        ptav_map = {
            data["id"]: {
                "attribute": attribute_data.get(data["attribute_id"][0]),
                "value": data["name"],
            }
            for data in ptav_data
            if data["attribute_id"]
        }
        return {
            product_id: [
                {
                    "name": ptav_map[ptav_id]["attribute"]["export_name"],
                    "value": ptav_map[ptav_id]["value"],
                }
                for ptav_id in value_ids
                if ptav_id in ptav_map
                and ptav_map[ptav_id]["attribute"]
                and ptav_map[ptav_id]["attribute"]["shoppingfeed_export"]
            ]
            for product_id, value_ids in product_ptav_ids.items()
        }

    def _get_no_variant_attributes(self, products, product_data):
        template_ids = {
            data["product_tmpl_id"][0]
            for data in product_data.values()
            if data["product_tmpl_id"]
        }
        if not template_ids:
            return {}
        lines_data = products.env["product.template.attribute.line"].search_read(
            [("product_tmpl_id", "in", list(template_ids))],
            ["attribute_id", "product_tmpl_id", "value_ids"],
            order="sequence, attribute_id, id",
        )
        attribute_ids = {
            data["attribute_id"][0] for data in lines_data if data["attribute_id"]
        }
        attribute_data = self._get_attribute_data(products, attribute_ids)
        value_ids = {
            value_id for data in lines_data for value_id in data.get("value_ids", [])
        }
        value_names = {}
        if value_ids:
            value_names = {
                data["id"]: data["name"]
                for data in products.env["product.attribute.value"]
                .browse(value_ids)
                .read(["name"])
            }
        result = {}
        for data in lines_data:
            attribute_id = data["attribute_id"] and data["attribute_id"][0]
            attribute = attribute_data.get(attribute_id)
            if (
                not attribute
                or attribute["create_variant"] != "no_variant"
                or not attribute["shoppingfeed_export"]
                or not data["value_ids"]
            ):
                continue
            template_id = data["product_tmpl_id"][0]
            result.setdefault(template_id, []).append(
                {
                    "name": attribute["export_name"],
                    "value": ", ".join(
                        value_names[value_id]
                        for value_id in data["value_ids"]
                        if value_id in value_names
                    ),
                }
            )
        return result

    def _get_attribute_data(self, products, attribute_ids):
        if not attribute_ids:
            return {}
        return {
            data["id"]: {
                "create_variant": data["create_variant"],
                "export_name": data["shoppingfeed_code_name_attribute"] or data["name"],
                "shoppingfeed_export": data["shoppingfeed_export"],
            }
            for data in products.env["product.attribute"]
            .browse(attribute_ids)
            .read(
                [
                    "create_variant",
                    "name",
                    "shoppingfeed_code_name_attribute",
                    "shoppingfeed_export",
                ]
            )
        }

    def _get_base_prices(self, store, products):
        currency = (
            store.pricelist_id.currency_id
            if store.pricelist_id
            else store.company_id.currency_id
        )
        if store.pricelist_id:
            prices = self._get_pricelist_prices(store, store.pricelist_id, products)
        else:
            prices = {product.id: product.lst_price or 0.0 for product in products}
        return {
            product_id: currency.round(price) for product_id, price in prices.items()
        }

    def _get_pricelist_prices(self, store, pricelist, products):
        return pricelist._get_products_price(products, 1.0, None)

    def _get_taxes_by_key(self, store, products, product_data):
        if not store.include_taxes_in_price:
            return {}
        tax_keys = {
            tuple(data["taxes_id"])
            for data in product_data.values()
            if data["taxes_id"]
        }
        return {
            tax_key: products.env["account.tax"]
            .browse(tax_key)
            ._filter_taxes_by_company(store.company_id)
            for tax_key in tax_keys
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

    def _get_main_images(self, products, product_data=None):
        if product_data is None:
            return self._get_main_images_from_binary_fields(products)
        product_ids = list(product_data)
        template_ids = {
            data["product_tmpl_id"][0]
            for data in product_data.values()
            if data["product_tmpl_id"]
        }
        attachments = products.env["ir.attachment"].sudo()
        product_image_ids = set(
            attachments.search(
                [
                    ("res_model", "=", "product.product"),
                    ("res_field", "=", "image_variant_1920"),
                    ("res_id", "in", product_ids),
                ]
            ).mapped("res_id")
        )
        template_image_ids = set(
            attachments.search(
                [
                    ("res_model", "=", "product.template"),
                    ("res_field", "=", "image_1920"),
                    ("res_id", "in", list(template_ids)),
                ]
            ).mapped("res_id")
        )
        return {
            product_id: product_id in product_image_ids
            or (
                data["product_tmpl_id"]
                and data["product_tmpl_id"][0] in template_image_ids
            )
            for product_id, data in product_data.items()
        }

    def _get_main_images_from_binary_fields(self, products):
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
        self._add_product_base_info(
            store, product_el, product, catalog_context, batch_context
        )
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

    def _get_batch_product_data(self, product, batch_context=None):
        if not batch_context:
            return {}
        return batch_context["product_data"].get(product.id, {})

    def _add_product_base_info(
        self, store, product_el, product, catalog_context, batch_context
    ):
        product_data = batch_context["product_data"][product.id]
        base_url = catalog_context["base_url"]
        if store.use_product_id_as_sku:
            sku_value = str(product.id)
        elif store.custom_sku_field_id:
            sku_value = product_data.get(store.custom_sku_field_id.name) or str(
                product.id
            )
        else:
            sku_value = product_data["default_code"] or str(product.id)
        etree.SubElement(
            product_el, "reference"
        ).text = f"{sku_value}_{store.country_id.code}"
        etree.SubElement(product_el, "gtin").text = product_data["barcode"] or ""
        etree.SubElement(product_el, "name").text = etree.CDATA(
            product_data["name"] or ""
        )
        if product_data["website_url"]:
            product_url = base_url + product_data["website_url"]
            etree.SubElement(product_el, "link").text = etree.CDATA(product_url)
        if product_data["weight"]:
            etree.SubElement(product_el, "weight").text = str(product_data["weight"])
        if product_data["product_brand_id"]:
            brand_el = etree.SubElement(product_el, "brand")
            etree.SubElement(brand_el, "name").text = etree.CDATA(
                batch_context["brand_names"].get(
                    product_data["product_brand_id"][0], ""
                )
            )
        if product_data["sf_forced_category_id"]:
            category_id = product_data["sf_forced_category_id"][0]
        else:
            category_id = next(
                (
                    category_id
                    for category_id in product_data["public_categ_ids"]
                    if category_id in catalog_context["allowed_categ_ids"]
                ),
                False,
            )
        if category_id:
            category_el = etree.SubElement(product_el, "category")
            etree.SubElement(category_el, "name").text = etree.CDATA(
                batch_context["category_names"].get(category_id, "")
            )
            etree.SubElement(category_el, "link").text = etree.CDATA(
                f"{base_url}/shop/category/{category_id}"
            )
        description_el = etree.SubElement(product_el, "description")
        full_desc = product_data["website_description"] or ""
        etree.SubElement(description_el, "full").text = etree.CDATA(full_desc)
        short_desc = product_data["description_sale"] or ""
        etree.SubElement(description_el, "short").text = etree.CDATA(short_desc)

    def _add_product_price(self, store, product_el, product, batch_context=None):
        product_data = self._get_batch_product_data(product, batch_context)
        price = self._get_base_price(store, product, batch_context)
        tax_ids = product_data.get("taxes_id") if product_data else product.taxes_id.ids
        if store.include_taxes_in_price and tax_ids:
            currency = (
                store.pricelist_id.currency_id
                if store.pricelist_id
                else store.company_id.currency_id
            )
            if batch_context:
                product_taxes = batch_context["taxes_by_key"][tuple(tax_ids)]
            else:
                product_taxes = product.env["account.tax"].browse(tax_ids)
                product_taxes = product_taxes._filter_taxes_by_company(store.company_id)
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
        product_data = self._get_batch_product_data(product, batch_context)
        if not store.use_actual_stock_state:
            quantity_value = store.default_quantity
        else:
            quantity_value = (
                self._get_quantity_value(store, product, batch_context) or 0
            )
            product_type = product_data.get("type") if product_data else product.type
            if product_type == "service":
                quantity_value = store.default_quantity
        sale_ok = product_data.get("sale_ok") if product_data else product.sale_ok
        if not sale_ok and store.force_zero_quantity_non_salable:
            quantity_value = 0
        etree.SubElement(product_el, "quantity").text = str(int(quantity_value))

    def _add_product_media(
        self, store, product_el, product, catalog_context, batch_context=None
    ):
        product_data = self._get_batch_product_data(product, batch_context)
        base_url = catalog_context["base_url"]
        images_el = etree.SubElement(product_el, "images")
        product_images = (
            product_data.get("product_template_image_ids")
            if product_data
            else product.product_template_image_ids.ids
        )
        if store.export_all_images:
            all_images = product_images
        else:
            all_images = product_images[: store.exported_image_count]
        if self._has_main_image(product, batch_context):
            etree.SubElement(images_el, "image", type="main").text = etree.CDATA(
                f"{base_url}/web/image/product.product/{product.id}/image_1920"
            )
        for image_id in all_images:
            etree.SubElement(images_el, "image").text = etree.CDATA(
                f"{base_url}/web/image/product.image/{image_id}/image_1920"
            )

    def _has_main_image(self, product, batch_context=None):
        if batch_context:
            return batch_context["main_images"].get(product.id, False)
        return self._get_main_images(product).get(product.id, False)

    def _add_product_attributes(  # noqa: C901
        self, store, product_el, product, batch_context=None
    ):
        product_data = self._get_batch_product_data(product, batch_context)
        attributes_el = etree.SubElement(product_el, "attributes")
        # Attributes that generate variants
        if batch_context:
            variant_attributes = batch_context["variant_attributes"].get(product.id, [])
        else:
            variant_attributes = []
            for value in product.product_template_attribute_value_ids:
                if not value.attribute_id.shoppingfeed_export:
                    continue
                variant_attributes.append(
                    {
                        "name": value.attribute_id.shoppingfeed_code_name_attribute
                        or value.attribute_id.name,
                        "value": value.name,
                    }
                )
        for attribute in variant_attributes:
            attr_el = etree.SubElement(attributes_el, "attribute")
            etree.SubElement(attr_el, "name").text = attribute["name"]
            etree.SubElement(attr_el, "value").text = attribute["value"]
        # Attributes that do NOT generate variants
        if batch_context:
            template_id = product_data["product_tmpl_id"][0]
            no_variant_attributes = batch_context["no_variant_attributes"].get(
                template_id, []
            )
        else:
            no_variant_attributes = []
            for line in product.product_tmpl_id.attribute_line_ids.filtered(
                lambda line_var: (
                    line_var.attribute_id.create_variant == "no_variant"
                    and line_var.attribute_id.shoppingfeed_export
                )
            ):
                if line.value_ids:
                    no_variant_attributes.append(
                        {
                            "name": line.attribute_id.shoppingfeed_code_name_attribute
                            or line.attribute_id.name,
                            "value": ", ".join(line.value_ids.mapped("name")),
                        }
                    )
        for attribute in no_variant_attributes:
            attr_el = etree.SubElement(attributes_el, "attribute")
            etree.SubElement(attr_el, "name").text = attribute["name"]
            etree.SubElement(attr_el, "value").text = attribute["value"]
        if store.additional_attribute_field_ids:
            for attr_field in store.additional_attribute_field_ids:
                field = attr_field.field_id
                value = (
                    product_data.get(field.name)
                    if product_data
                    else getattr(product, field.name, False)
                )
                if not value:
                    continue
                attr_el = etree.SubElement(attributes_el, "attribute")
                attr_name = (
                    attr_field.custom_name or field.field_description or field.name
                )
                etree.SubElement(attr_el, "name").text = attr_name
                if field.ttype == "many2one":
                    if isinstance(value, tuple | list):
                        attr_value = value[1] if len(value) > 1 else str(value[0])
                    else:
                        attr_value = (
                            value.display_name
                            if hasattr(value, "display_name")
                            else str(value.id)
                        )
                    etree.SubElement(attr_el, "value").text = attr_value
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
