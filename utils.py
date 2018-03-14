# encoding: utf-8
from __future__ import unicode_literals

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


WEIGHT_LIFTER_EMOJI = u'🏋️'
THUMBS_UP_EMOJI = u'👍'
THUMBS_DOWN_EMOJI = u'👎'

DAYS_NAME = 'Sunday Monday Tuesday Wednesday Thursday Friday Saturday'.split()
HEBREW_DAYS_NAME = 'ראשון שני שלישי רביעי חמישי שישי שבת'.split()


def upper_first_letter(name):
    return name[0].upper() + name[1:].lower()


def get_db_session(db_con_string):
    from models import Base
    engine = create_engine(db_con_string)
    Base.metadata.bind = engine
    DBSession = sessionmaker(bind=engine)
    return DBSession()