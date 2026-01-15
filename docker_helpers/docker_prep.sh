apt-get update && apt-get install -y git
if [ -d "bitcart-docker" ]; then echo "existing bitcart-docker folder found, pulling instead of cloning."; git pull; fi
if [ ! -d "bitcart-docker" ]; then echo "cloning bitcart-docker"; git clone https://github.com/bitcart/bitcart-docker bitcart-docker; fi

# Environment variables for docker
#export BITCART_HOST=bitcart.local
export BITCART_CRYPTOS=btc
export BTC_LIGHTNING=True
export BITCART_ADDITIONAL_COMPONENTS=tor btc-ln

# TO be able to open channels remotely:
export BTC_LIGHTNING_LISTEN=0.0.0.0:9735
export BTC_LIGHTNING_GOSSIP=true
# add our custom sauce to the compose script (enables electrum listening on port 9735)
export BITCARTGEN_DOCKER_IMAGE=bitcart/docker-compose-generator:local