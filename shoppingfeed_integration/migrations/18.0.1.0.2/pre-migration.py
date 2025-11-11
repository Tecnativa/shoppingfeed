def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        ALTER TABLE shoppingfeed_channel
        ADD COLUMN IF NOT EXISTS sf_channel_name VARCHAR
        """
    )
    cr.execute(
        """
        UPDATE shoppingfeed_channel
        SET sf_channel_name = name
        WHERE sf_channel_name IS NULL
        """
    )
