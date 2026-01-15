import datetime,os
from datetime import datetime
from typing import List,Dict,Set,Union,Tuple,Any,Optional
from peewee import Model, CharField, BigIntegerField, DateTimeField, IntegerField, SqliteDatabase,FloatField,BooleanField

from config import NODE_CRITERIA_MINIMUM_CHANNELCOUNT, NODE_CRITERIA_MINIMUM_AGE,NODE_CRITERIA_MINIMUM_CAPACITY
import json

node_db = SqliteDatabase('known_ln_nodes.db')

class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, LightningNode):
            #return obj.to_json()
            return obj.__dict__['__data__']
        elif isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

class BaseModel(Model):
    class Meta:
        database = node_db


class LightningNode(BaseModel):
    # All units in sats, time durations in seconds
    # Remember to call self.set_oldest_known_date() when creating nodes so oldest_known_date can be sorted on
    node_address:str = CharField(unique=True, primary_key=True) # pubkey, LOWERCASE
    min_channel_size:Optional[int] = BigIntegerField(null=True) # minimum channel size found on magma (smallest it will accept, not smallest it has)
    country:Optional[str] = CharField(null=True) # country found on any indexer, not currently used for anything
    oldest_channel:Optional[DateTimeField] = DateTimeField(null=True) # oldest channel found on any indexer
    number_of_channels:Optional[int]=IntegerField(null=True) # highest # found on any indexer
    total_capacity:Optional[int] = BigIntegerField(null=True) # highest amount found on any indexer
    smallest_channel_size:Optional[int]=BigIntegerField(null=True) # smallest known channel of this node
    oldest_known_date:datetime=DateTimeField(default=datetime.now()) # oldest possible birth date of this node/when it was created
    tor_address:Optional[str] = CharField(null=True)  # abc.onion:1781
    ipv4_address:Optional[str] = CharField(null=True)  # x.x.x.x:xxxx
    ipv6_address:Optional[str] = CharField(null=True)  # xxx:xx:85a3:0:0:8a2e:370:7334
    last_magma_query:datetime=DateTimeField(default=datetime.now())
    magma_queries: int = IntegerField(default=0)
    last_channel_creation_attempt:Optional[datetime] = DateTimeField(null=True)  # last attempt to create a channel with this node
    remote_close_count:int=IntegerField(default=0) # how many times this LN node has closed a channel we have open with it
    failed_uptime_checks:int=IntegerField(default=0)
    total_uptime_checks:int=IntegerField(default=0)
    last_seen_online: Optional[datetime] = DateTimeField(null=True)

    def needs_magma_update(self,update_frequency_in_days:int)->bool:
        """
        Returns True if we should query Magma for this node's details again
        """
        time_between_insertion = datetime.now() - self.last_magma_query

        if time_between_insertion.days > update_frequency_in_days:
            return True
        else:
            return False
    def get_oldest_known_date(self)->Optional[DateTimeField]:
        return max(self.oldest_known_date,self.oldest_channel)
    def set_oldest_known_date(self)->Optional[DateTimeField]:
        self.oldest_known_date=max(self.oldest_known_date,self.oldest_channel)
    def get_ipv4_uri(self)->str:
        """
        Returns IPv6 URI if possible, otherwise None
        """
        if not self.ipv4_address:
            return None
        return f"{self.node_address}@{self.ipv4_address}"
    def get_amboss_url(self)->str:
        """
        Returns IPv6 URI if possible, otherwise None
        """
        return f"https://amboss.space/node/{self.node_address.lower()}"

    def to_json(self,)->str:
        return json.dumps(self.__dict__['__data__'], cls=CustomEncoder)

    @classmethod
    def from_json(cls, data:dict):
        # Convert all datetime fields
        for field in {'oldest_channel','oldest_known_date','last_magma_query','last_channel_creation_attempt','last_seen_online'}:
            if field in data and data[field] is not None:
                data[field] = datetime.fromisoformat(data[field])
        return cls(**data)
class LightningChannel(BaseModel):
    # All units in sats, time durations in seconds
    # Remember to call self.set_oldest_known_date() when creating nodes so oldest_known_date can be sorted on
    channel_point:str = CharField(unique=True, primary_key=True) # channel point like 658c3cf4e8b798bd1f1d805c2de37fffsfsffba644af193c9e87d5e2adb:0 LOWERCASE
    last_seen_online: Optional[datetime] = DateTimeField(null=True) # not used for anything yet
    cooperative_close_requested: Optional[datetime] = DateTimeField(null=True) # date of FIRST request to cooperatively close

def dict_to_node(mydict:Dict[str,str])->Optional[LightningNode]:
    """
    Given a dict, make a lightning node. Does not save it, just creates it.
    Assumes you have already verified this node does NOT exist
    """
    if 'node_address' not in mydict:
        return None
    new_object = LightningNode(node_address=mydict['node_address'])
    for k, v, in mydict.items():
        if k.startswith('_'):
            continue
        if not v:
            continue
        field = LightningNode._meta.fields[k]
        if isinstance(field, CharField):
            setattr(new_object, k, v)
        elif isinstance(field, IntegerField):
            setattr(new_object, k, int(v))
        elif isinstance(field, FloatField):
            setattr(new_object, k, float(v))
        elif isinstance(field, BooleanField):
            setattr(new_object, k, bool(v))
        elif isinstance(field, DateTimeField):
            setattr(new_object, k, datetime.fromisoformat(v))
        else:
            print(f'Unknown field type: {field}')
    return new_object
def is_node_blacklisted(node:LightningNode)->Tuple[bool,str]:
    """
    Returns True,reason if we should not open a channel to this node. False,None otherwise
    """
    if not node.ipv4_address:
        return True, 'NO_IPV4'
    if node.remote_close_count>2:
        return True,'REMOTE_CLOSE_COUNT'
    if not node.number_of_channels:
        return True, 'UNKNOWN_CHANNEL_COUNT'
    if node.number_of_channels<NODE_CRITERIA_MINIMUM_CHANNELCOUNT:
        return True, 'MIN_CHANNEL_COUNT'
    if not node.total_capacity:
        return True, 'UNKNOWN_CAPACITY'
    if node.total_capacity<NODE_CRITERIA_MINIMUM_CAPACITY:
        return True, 'LOW_CAPACITY'
    oldest_known_date=node.get_oldest_known_date()
    if not oldest_known_date:
        return True, 'NO_OLDEST_KNOWN_DATE'
    elapsed_time=datetime.now()-oldest_known_date
    elapsed_time_in_days=elapsed_time.days
    if elapsed_time_in_days<NODE_CRITERIA_MINIMUM_AGE:
        return True, 'NOT_OLD_ENOUGH'
    return False,'False'

node_db.connect()
node_db.create_tables([LightningNode,LightningChannel])
print("LN Node database initialized successfully")