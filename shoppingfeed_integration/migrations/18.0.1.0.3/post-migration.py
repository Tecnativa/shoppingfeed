# Copyright 2026 Tecnativa - Carlos Lopez
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.m2o_to_x2m(
        env.cr,
        env["shoppingfeed.store.carrier.map"],
        "shoppingfeed_store_carrier_map",
        "delivery_carrier_ids",
        "delivery_carrier_id",
    )
