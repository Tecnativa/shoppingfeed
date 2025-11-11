M2M_TABLE = "shoppingfeed_channel_shoppingfeed_store_rel"


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)",
        (M2M_TABLE,),
    )
    if not cr.fetchone()[0]:
        return
    cr.execute(
        """
        ALTER TABLE shoppingfeed_channel
        ADD COLUMN IF NOT EXISTS store_id INTEGER
        REFERENCES shoppingfeed_store(id) ON DELETE CASCADE
        """
    )
    cr.execute(
        """
        UPDATE shoppingfeed_channel c
        SET store_id = (
            SELECT shoppingfeed_store_id
            FROM shoppingfeed_channel_shoppingfeed_store_rel
            WHERE shoppingfeed_channel_id = c.id
            LIMIT 1
        )
        """
    )
    cr.execute("DELETE FROM shoppingfeed_channel WHERE store_id IS NULL")
