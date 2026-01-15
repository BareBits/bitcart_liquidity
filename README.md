# Bitcart Bitcoin Lightning Liquidity Helper
This script makes it easy to manage inbound Bitcoin Lightning liquidity for your Bitcart store. While Bitcart supports lightning, 
it leaves you to figure out how to get inbound liquidity. Without inbound liquidity, you can't
receive payments via lightning. 

This script supports having multiple stores and manages a wallet *liquidityhelper* for each store. **This script charges a 2% fee** which is assessed over all incoming payments to wallets the script manages. Network fees are included in this, so if this script manages your funds and spends 0.5% on network fees, it only "charges" you 1.5% so your net fee remains at 2%

## ⚠️ Warning
This is alpha software and should not be deployed on production systems. There are bugs which will probably cause you to lose money. We are not responsible for any lost funds.

## Requirements
In order to use this script, you must have:
- A server with Bitcart running
- The ability to execute commands/python scripts on that server
- Some on-chain funds to open lightning channels with
- A lightning address that can occasionally receive payments FROM your Bitcart server. Good, free custodial options include Strike and CoinOS. For non-custodial, check out Zeus wallet.

If deployed via docker, you must have the following environment variables set. You can set these like so and then re-run setup.sh in bitcart-docker to seamlessly upgrade:
```
export BITCART_CRYPTOS=btc
export BTC_LIGHTNING=True
export BTC_LIGHTNING_LISTEN=0.0.0.0:9735
export BITCART_ADDITIONAL_COMPONENTS=btc-ln
export BTC_LIGHTNING_GOSSIP=true 
export BITCART_BITCOIN_EXPOSE=true
export BTC_DEBUG=true
export ALLOW_INCOMING_CHANNELS=true
```


## How to use
1. Download this repository with git clone
2. Provide the proper config variables, you can do this via environment variables or by copying `config.py` to `user_config.py` and modifying from there. Environment variables override anything found in config files. At a minimum, you need to provide `CASHOUT_LIGHTNING_ADDRESS` and `AUTH_TOKEN`. You can find your auth token in Bitcart by going to User Profile -> API keys.
3. Run `pip install -r requirements.txt`
3. Run `python3 liquidityhelper.py`

## How it works
- The script monitors the amount of available inbound liquidity on your server. If liquidity is below your set threshold, it will open new lightning channels using your on-chain funds, then empty those channels to your payout lightning address (so you now have inbound liquidity)
- Any time there are funds in lightning, it will instruct Bitcart to send those funds to your payout address
- You will occasionally have to "top up" your Bitcart wallet to re-open channels when existing channels get closed

## Privacy
This script runs locally only and does not report your transaction data or other private information to any external place. The script queries our server for a list of lightning nodes (and queries Magma for information about those nodes) and manages its node list autonomously.

## Contributing
Contributions in the form of PRs are welcome, please see `DESIGN.md` for our design principles and `ROADMAP.md` for planned/desired features.

## License
You are free to use and modify this script as you wish provided you do not remove the fee component. See LICENSE & USE_POLICY and for full terms and details.

BareBits is self-hosted payment processing software. You may download, deploy, and modify it on your own infrastructure (subject to applicable open-source and third-party licenses). You are solely responsible for configuration, security hardening, key custody, compliance, and any transactions processed through your instance. To the maximum extent permitted by law, BareBits disclaims liability for your deployment, modifications, integrations, and downstream use, and provides the Software “as is” with no warranties. BareBits does not provide a hosted service unless you have a separate written Service Agreement.

