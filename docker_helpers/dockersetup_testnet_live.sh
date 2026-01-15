# import main variables & do docker prep (download git repo, set environment variables)
source ./docker_prep.sh

export BITCART_HOST=testnet.getbarebits.com

# DEV MODE STUFF
export BTC_DEBUG=true # get better logs from electrum, should be removed in prod
export BITCART_REVERSEPROXY=nginx # disable SSL, should be removed in prod
export BITCART_BITCOIN_EXPOSE=false # enable access to bitcart electrum installation outside of docker container, should be removed in prod
export BTC_NETWORK=testnet # run Bitcoin on testnet

cd bitcart-docker
./setup.sh


