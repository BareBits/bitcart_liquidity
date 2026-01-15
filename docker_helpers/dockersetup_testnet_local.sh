# import main variables & do docker prep (download git repo, set environment variables)
source ./docker_prep.sh
export BITCART_HOST=bitcart.local

# DEV MODE STUFF
# get better logs from electrum, should be removed in prod
export BTC_DEBUG=true
# disable SSL, should be removed in prod
export BITCART_REVERSEPROXY=nginx
# enable access to bitcart electrum installation outside of docker container, should be removed in prod
export BITCART_BITCOIN_EXPOSE=true
#export BITCART_BITCOIN_PORT=127.0.0.1:7615
# run Bitcoin on testnet
export BTC_NETWORK=testnet

cd bitcart-docker
./setup.sh

