+=difficulty
## Version .1: MVP Released Jan 2026
- Able to automatically manage liquidity for lightning channels
## Version .2: Unknown release date
- Capture env variables, save to db
- Add some obfuscation code to make it harder to remove/disable fee
- Add support for user notification when top-ups needed, limited to certain number of messages per time period. Bitcart API has a feature for this iirc
- ++Add support for affiliate fees somehow
- SimpleDateTimeField may not be working as intended since name is not a primary key or unique, look into that
- Sanitize input from LNURL requests, verify they are valid invoices
- +In classes.BitcartAPI.create_store() add support for custom logo link etc

## Version .3: Unknown release date
- All functions in classes.BitcartAPI should use _query instead of making queries themselves. This adds pagination and eventually retries
## Version .4: Unknown release date

## Version .5: Unknown release date
- ++++Turn this into a Bitcart plugin
## Version .6: Unknown release date