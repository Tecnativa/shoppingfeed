from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    env.cr.execute(
        """
        UPDATE sale_order
        SET client_order_ref = shoppingfeed_reference
        WHERE shoppingfeed_reference IS NOT NULL
          AND shoppingfeed_reference != ''
          AND (client_order_ref IS NULL OR client_order_ref = '')
        """
    )
