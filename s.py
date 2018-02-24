from models import *
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine


def create_session():
    # engine = create_engine('sqlite:///sqlalchemy_example.db')
    engine = create_engine('')
    Base.metadata.bind = engine
    DBSession = sessionmaker(bind=engine)
    return DBSession()

session = create_session()

days = 'sunday monday tuesday wednesday thursday friday saturday'.split()

# session.add_all([Day(name=day) for day in days])
session.commit()
