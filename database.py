import peewee
from peewee import *
from datetime import datetime,timedelta
import os
from typing import Optional,List,Dict,Set,Iterable,Tuple,Any
DATABASE_NAME = 'liquidityhelper.sqlite'
db = SqliteDatabase(DATABASE_NAME)

class BaseModel(Model):
    """Base model that all models will inherit from"""

    class Meta:
        database = db

class LOrder(BaseModel):
    """Model for liquidity orders table"""
    order_id = CharField(max_length=255)
    date = DateTimeField()

    class Meta:
        table_name = 'lrequests'

class SimpleDateTimeField(BaseModel):
    """Model for liquidity orders table"""
    name = CharField(max_length=255)
    date = DateTimeField()
class Notification(BaseModel):
    """Model for notifications table"""
    type =CharField(max_length=15) # Valid options: LOWLIQ
    body = TextField(null=True)
    date_sent = DateTimeField(null=True)
class LastRunTracker(BaseModel):
    name = CharField(unique=True)
    last_run = DateTimeField(default=datetime.now())
class SimpleCacheField(BaseModel):
    """Model for cache table"""
    name = CharField(max_length=100)
    date = DateTimeField()
    content=TextField()
    expiry_in_seconds = IntegerField()

    @classmethod
    def delete_expired(cls):
        """Delete all expired cache entries.

        Returns:
            int: Number of deleted entries
        """
        now = datetime.now()
        # Delete all records where current time > date + expiry_in_seconds
        count = cls.delete().where(
            cls.date + cls.expiry_in_seconds < now.timestamp()
        ).execute()
        return count
class SimpleVariable(BaseModel):
    name = CharField(max_length=100,primary_key=True)
    value = CharField()


def create_order(order_id, date=None):
    """
    Create a new liquidity request entry

    Args:
        order_id (str): Order ID
        date (datetime, optional): Date of order. Defaults to current time.

    Returns:
        LRequest: Created request object
    """
    if date is None:
        date = datetime.now()

    request = LOrder.create(order_id=order_id, date=date)
    print(f"Created order with ID: {order_id}")
    return request
def count_notifications_sent(since_date:Optional[datetime]=None, notification_type:Optional[str]=None)->int:
    """
    Count how many notifications have been sent since datetime x of type y.
    """
    found_records=[]
    records=Notification.select()
    for record in records:
        found_records.append(str(record.__dict__))
    pass
    if notification_type:
        if since_date:
            found_notifications: int = Notification.select().where(Notification.date_sent >= since_date,
                                                                                  Notification.type == notification_type).count()
        else:
            found_notifications: int = Notification.select().where(Notification.date_sent.is_null(False),
                                                                                  Notification.type == notification_type).count()
    else:
        if since_date:
            found_notifications: int = Notification.select().where(Notification.date_sent >= since_date,
                                                                              Notification.date_sent.is_null(False)).count()
        else:
            found_notifications: int = Notification.select().where(Notification.date_sent !=None,
                                                                              Notification.date_sent.is_null(False)).count()

    return found_notifications

db.connect(reuse_if_open=True)
USED_TABLES=[SimpleDateTimeField,SimpleCacheField,LOrder,LastRunTracker,SimpleVariable,Notification]
db.create_tables(USED_TABLES, safe=True)
print(f"Database '{DATABASE_NAME}' initialized successfully")