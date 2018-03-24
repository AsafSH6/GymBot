# encoding: utf-8
from __future__ import unicode_literals


WEIGHT_LIFTER_EMOJI = u'🏋️'
THUMBS_UP_EMOJI = u'👍'
THUMBS_DOWN_EMOJI = u'👎'

DAYS_NAME = 'Sunday Monday Tuesday Wednesday Thursday Friday Saturday'.split()
HEBREW_DAYS_NAME = 'ראשון שני שלישי רביעי חמישי שישי שבת'.split()


def upper_first_letter(name):
    return name[0].upper() + name[1:].lower()


def get_week_days():
    from gym_bot_app.db.models import Day
    return Day.get_week_days()
