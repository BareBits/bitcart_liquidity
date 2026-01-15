# import main variables & do docker prep (download git repo, set environment variables)
source ./docker_prep.sh

export BITCART_HOST=bitcart.getbarebits.com

# DEV MODE STUFF
# get better logs from electrum, should be removed in prod
export BTC_DEBUG=true
# disable SSL, should be removed in prod
export BITCART_REVERSEPROXY=nginx
# enable access to bitcart electrum installation outside of docker container, should be removed in prod
#export BITCART_BITCOIN_EXPOSE=false
# run Bitcoin on testnet
export BTC_NETWORK=testnet

cd bitcart-docker
./setup.sh


