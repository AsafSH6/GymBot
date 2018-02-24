# encoding: utf-8
from __future__ import unicode_literals

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base

WEIGHT_LIFTER_EMOJI = u'🏋️'
THUMBS_UP_EMOJI = u'👍'
THUMBS_DOWN_EMOJI = u'👎'

DAYS_NAME = 'sunday monday tuesday wednesday thursday friday saturday'.split()
HEBREW_DAYS_NAME = 'ראשון שני שלישי רביעי חמישי שישי שבת'.split()


def upper_first_letter(name):
    return name[0].upper() + name[1:]


def get_db_session():
    # engine = create_engine('sqlite:///sqlalchemy_example.db')
    engine = create_engine('postgres://bmkeltax:mj9riixCKwtgLVg30HMk7x_KX8lTgZXS@horton.elephantsql.com:5432/bmkeltax')
    Base.metadata.bind = engine
    DBSession = sessionmaker(bind=engine)
    return DBSession()