## Store Setup

### Create and authenticate your store

1. Go to **Shoppingfeed → Stores**
2. Click **New** and fill:
   - **Username**: Shoppingfeed API email
   - **Password**: Shoppingfeed API password
3. Click **Get Token** button
   - Automatically retrieves: catalog ID, channels, country, and language

### Configure product export

In the store form, configure these tabs:

#### Exportable Products tab

- **Export only selected**: Only export products with "Export to Shoppingfeed" enabled
- **Export Product Types**: Select product types to include (Goods, Services, Combos)
- **Export Rules**: Control which products to include:
  - Out of stock products
  - Archived products
  - Non-salable products

#### Stock tab

- **Use actual stock state**: Use real quantities vs default quantity
- **Quantity type**: Salable (on-hand) or Virtual (forecasted)
- **Default quantity**: Quantity for products without stock tracking
- **Force zero quantity non salable**: Set 0 for non-salable products
- **Update quantities realtime**: Push stock changes immediately to Shoppingfeed

#### Prices tab

- **Pricelist**: Optional pricelist for computing export prices

#### Attributes tab

- **Use product ID as SKU**: Use product ID instead of default code
- **Custom SKU field**: Select custom field for SKU (optional)
- **Additional attribute fields**: Add custom product fields to export

#### Images tab

- **Export all images**: Include all product images
- **Exported image count**: Limit number of images (if not exporting all)

#### Categories tab

- **Allowed categories**: Restrict export to specific product categories

#### Shipping tab

- **Default delivery carrier**: Fallback carrier for unmapped carriers
- **Carrier mappings**: Map Shoppingfeed carrier names to Odoo carriers
  - Add lines with Shoppingfeed carrier name and corresponding Odoo carrier

#### Orders tab

- **Import orders**: Enable automatic order import
- **Default payment term**: Payment terms for imported orders
- **Default payment mode**: Payment mode for imported orders
- **Default order type**: Order type for imported orders
- **Marketplace customer groups**: Map channels to specific order types
  - Add lines with Channel and Order Type

## Product Setup

### Mark products for export

1. Open a product
2. In **Shoppingfeed** tab:
   - Enable **Export to Shoppingfeed** (if store requires it)
   - Select **Shoppingfeed Stores** to export this product to

**Note**: Products need default code (internal reference) to export.

## Catalog Feed

After configuration, your XML catalog feed is available at:

```
https://yourdomain.com/catalog/{catalog_id}.xml
```

Share this URL with Shoppingfeed for product synchronization.

