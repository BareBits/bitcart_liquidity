import json

import node_database
from node_database import LightningNode
from typing import List,Dict,Set,Union,Tuple,Optional,Iterable
# Helper script to create json database of nodes
if __name__=='__main__':
    to_dump=[]
    used_uris=set()
    # include manually curated nodes
    manual_nodes = [
        {"uri": "031b301307574bbe9b9ac7b79cbe1700e31e544513eae0b5d7497483083f99e581@45.79.192.236:9735",
                     "comment": "zeus"},
                    {"uri": "026165850492521f4ac8abd9bd8088123446d126f648ca35e60f88177dc149ceb2@143.202.162.204:9735",
                     "comment": "boltz"},
                    {"uri": "03864ef025fde8fb587d989186ce6a4a186895ee44a926bfc370e2c366597a3f8f@3.33.236.230:9735",
                     "comment": "acinq"},
                    {"uri": "03abf6f44c355dec0d5aa155bdbdd6e0c8fefe318eff402de65c6eb2e1be55dc3e@18.221.179.73:9735",
                     "comment": "wobloz"},
                    {"uri": "02c953421bc7f07be6052920e46843d11e6d3ffc9986177c91f140d76c6ed3a3d4@132.232.253.4:9735",
                     "comment": "LNT"},
                    {"uri": "03abf6f44c355dec0d5aa155bdbdd6e0c8fefe318eff402de65c6eb2e1be55dc3e@18.221.179.73:9735",
                     "comment": "OpenNode"},
                    {"uri": "0294ac3e099def03c12a37e30fe5364b1223fd60069869142ef96580c8439c2e0a@47.242.126.50:26658",
                     "comment": "OKX"},
                    {"uri": "033d8656219478701227199cbd6f670335c8d408a92ae88b962c49d4dc0e83e025@34.65.85.39:9735",
                     "comment": "BFX"},
                    {"uri": "037659a0ac8eb3b8d0a720114efc861d3a940382dcfa1403746b4f8f6b2e8810ba@34.78.139.195:9735",
                     "comment": "Nicehash"}
                    ]
    for node in manual_nodes:
        to_dump.append(node)
        used_uris.add(node['uri'])

    node_list:List[LightningNode]=LightningNode.select()
    for node in node_list:
        if not node_database.is_node_blacklisted(node)[0]:
            ipv4_uri=node.get_ipv4_uri()
            if ipv4_uri not in used_uris:
                my_dict={'uri':ipv4_uri,'comment':'auto'}
                to_dump.append(my_dict)
                used_uris.add(ipv4_uri)

    with open("default_channel_partners.json", "w") as json_file:
        json.dump(to_dump, json_file)
