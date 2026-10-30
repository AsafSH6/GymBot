"""Helpers shared by the test modules."""
import os

import mongomock
from mongoengine import connect, disconnect
from mongoengine.connection import get_db


def connect_test_db():
    """Connect to mongomock, an in-memory MongoDB, or to the MongoDB at TEST_MONGODB_URL if set.

    The tests wipe the database, so the name of a real one must contain "test".

    """
    if os.getenv('TEST_MONGODB_URL'):
        connect(host=os.environ['TEST_MONGODB_URL'])
        db_name = get_db().name
        if 'test' not in db_name:
            disconnect()
            raise RuntimeError('Refusing to wipe {!r}: TEST_MONGODB_URL must name a test database'.format(db_name))
    else:
        connect('gymbot_test', mongo_client_class=mongomock.MongoClient)


def disconnect_test_db():
    disconnect()
