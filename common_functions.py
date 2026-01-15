# Short functions used by various files INCLUDING config file
from typing import List,Dict,Tuple,Iterable,Any,Set
import math
def is_integer(string):
    try:
        int(string)
        return True
    except ValueError:
        return False


def is_float(string):
    try:
        temp=float(string)
        if temp.is_integer():
            return False
        return True
    except ValueError:
        return False


def sats_to_btc(sats:int)->float:
    return sats/100000000


def btc_to_sats(btc:float)->int:
    return int(btc*100000000)
def sats_to_max_channel_size(sats:int):
    """
    Given a number of sats, what is the biggest single channel we can create?
    Assumes all of these sats are safe to spend and we have enough reserves for existing channels
    """
    for potential_channel_size in reversed(range(1,sats)):
        output=onchain_reserves_to_keep_for_channel(potential_channel_size)
        if output+potential_channel_size<sats:
            return potential_channel_size
    return 0


def onchain_reserves_to_keep_for_channel(sats:int)->int:
    """
    Given channel of a certain size (including reserves within the channel), keep this many addl sats in on-chain wallet. Hardcoding this as
    11,000 sats for now. This is what I found was the approximate actual number when testing w Electrum wallet on Mutinynet.
    If you pick a lower number, Electrum complains that you don't have enough fees.
    is dynamically calculated.
    Unsure if this is a flat number or calculated based on the number of channels you have
    """
    # I tested every 1,000 sats between 10k and 15k. 10,001 was not sufficient, 10,500 was, leaving a bit for flex in
    # case this is based on fee environment. Testing was in a 1 sat/vbyte environment

    return 11000
def liquidity_to_channel_size(sats:int)->int:
    """
    Given amount of sats, how large does the channel size need to be to support this amount of inbound liquidity
    """
    # prevents channel close from being split into unspendable transactions. Fixed amount
    # 546 is highest found limit hardcoded into electrum (see bitcoin.py in electrum code)
    dust_limit=546

    # channel reserve is unspendable returned only in event of cooperative close or the correct force close outcome.
    # MUST be larger than dust limit per lightning spec. Typically 1% of channel. This is consistent w reserved found in test
    # electrum wallet
    channel_reserve = sats * .01

    final_size=math.ceil(sats+dust_limit+max(channel_reserve,dust_limit))
    return final_size



def distribute_sats_over_channels(sats:int,channels:int)->List[int]:
    """
    Given amount of sats, equally divide it among channels. Assumes you are passing in sane, possible values.
    """
    if channels==1:
        return [sats]
    sats_per_channel=math.floor(sats/channels)
    remainder=sats-(sats_per_channel*channels)
    list_minus_one_channel=[sats_per_channel]*(channels-1)
    list_minus_one_channel.append(sats_per_channel+remainder)
    return list_minus_one_channel

def target_from_channel_sizes(channels:List[int],channel_buffer:int)->int:
    """
    Given a list of channel sizes we want, calculate the total sats it would take to create them and have enough left
    over for closing them if need be
    Channels: list of channel sizes we want in sats
    Channel_buffer: Amount of sats to keep to open/close a channel after creation
    """
    #find our own intended reserve
    own_reserve=channel_buffer*len(channels)

    # find electrums required reserve
    electrum_reserve=0
    for intended_channel_size in channels:
        dust_limit_sat = 20001  # don't know what this actually is
        electrum_reserve += max(intended_channel_size // 100, dust_limit_sat)

    # return the highest of the two reserve estimates plus channel amounts themselves
    return sum(channels)+(max(own_reserve,electrum_reserve))