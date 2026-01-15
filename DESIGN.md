## Purpose
liquidityhelper is a script to automatically manage liquidity for Bitcart merchants.
In order to do this, it must know a number of things, keep track of them all, and make decisions based on that information.

Keeping track of all this can get confusing, so this serves an authoritative resource on the project's logic flow and variables.

All of this logic is processed on a per-store basis. Bitcart can have multiple stores attached to the same wallet.

Each store has a `liquidityhelper` wallet managed by the software. Generally, other wallets are disregarded. Liquidity is managed on a per-store basis.

Money moves into the wallets via:
- Customer payment of invoices
- "Top-ups" by the Bitcart admin

Money moves out of wallets via:
- Payouts manually created in Bitcart admin interface by admin
- The "cashout" mechanism which moves on-chain funds into lightning, then sends them to the cashout address
- Fees are paid out in the same way cashouts are done

Design principles:
- Funds are kept separate between wallets. We assume the user may have some accounting reasons for keeping the wallets seperate in the first place.
- Persist as little data as possible. Data persistence makes testing more difficult.
- Do not interact with the wallet directly unless whatever you want to do can't be done via the Bitcart API. Wallet interactions should be written to be abstractable in the future so we can adapt code to other wallets
- Unless otherwise stated, all BTC units are in sats.
- Nothing should ever crash this script. Try/except everything and handle exceptions safely.
- Nothing, except access to the SQLite database, should assume we have access to the filesystem.

There are two sqlite databases for persisting data, one for the main liquidityhelper script and associated functions (liquidityhelper.sqlite), 
and one for the lightning node database for tracking the behavior of lighting nodes over time (known_ln_nodes.db).

## Variables:
MIN_INBOUND_LIQUIDITY # minimum amount of sats we want to have at any given time in live channels. Per wallet.
MIN_INBOUND_LIQUIDITY_PER_CHANNEL # don't create channels smaller than this size
MIN_CHANNEL_COUNT # minimum number of live channels we want for each wallet

## Logic
```
for each store:
    if we need more inbound liquidity (INBOUND_LIQUIDITY<MIN_INBOUND_LIQUIDITY or CHANNELS<MIN_CHANNELS):
        if we aren't due for a top_up (we want to create channels until we have as many funds as possible):
            move on-chain funds into LN channels
    if we are due for top-ups (INBOUND_LIQUIDITY<MIN_INBOUND_LIQUIDITY or CHANNELS<MIN_CHANNELS):
        calculate funds needed for top-up and display to the user
    if any cashouts are due:
        make cashouts via LN to cashout address
    if any fees are due:
        make fee payments via LN to fee address
    
```
### Reserve Amounts & Channel Size Calculations
Given any goal for an amount of inbound liquidity, we must calculate how much it would cost to get that liquidity and how
 many sats to keep in reserve for channel closes etc. This should be written in such a way that it can be expanded
to include things like renting liquidity. We must also know how much to ask the user to "top up"

If we are under our inbound liquidity goal:
- Given x sats of needed inbound liquidity over y channels, what is our list of intended channel sizes (liquidity only) (common_functions.distribute_sats_over_channels)
- Given x sats of inbound liquidity, how big would the channel itself need to be (channel itself has reserves built-in) (common_functions.liquidity_to_channel_size)
- Given a channels of x sats, how much would we need to keep in reserve to close it if needed (common_functions.onchain_reserves_to_keep_for_channel)
- How much additional reserve, if any, do we want to keep (flat amount or calculated amount) (0, but could later be incorporated) (not implemented)
- Doing all five in a row gets us the topup amount

If we are at or over our liquidity goal, we need to know how many sats are safe to spend and how to spend them
- Given existing channels, how much do we need to keep in reserve to close those channels (liquidityhelper.safe_to_spend)
- Given output from safe_to_spend, what is the biggest channel we can make? (common_functions.sats_to_max_channel_size)



## Code
All of the above functions are called from def main() and each function handles its own store looping. The main reason
for this is that some stores have multiple wallets and some wallets connect to multiple stores. How we treat those depends on the function, so a loop in main() would get complex quickly.
The other reason for this is so we can wrap each main section in its own `try..except` clause so the script never crashes and instead loops indefinitely

### Lightning Node Database
The database is seeded from a json file on the BareBits website. After that, the script autonomously manages the list of nodes,
 keeping track of which ones are "friendly", uptimes, etc. The script can also fetch new nodes from Magma and update the node info from their site, but heavy throttles are placed on this to be nice to their server. This is written in a way that can be extended to other providers.

### Logging
Logging notes:
- DEBUG: Detailed information, typically of interest only when diagnosing problems.
- INFO: Confirmation that things are working as expected
- WARNING: This is a potential problem, but also sometimes normally happens and it's fine
- ERROR: Some function has failed, but generally won't break the main functionality of the script
- CRITICAL: Some very important function has failed, and the script can't accomplish it's main duties as a result