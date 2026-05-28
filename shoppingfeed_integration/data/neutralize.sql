UPDATE shoppingfeed_store
   SET demo_mode = TRUE
 WHERE demo_mode IS DISTINCT FROM TRUE;
