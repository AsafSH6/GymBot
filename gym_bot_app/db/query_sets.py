# encoding: utf-8
from __future__ import unicode_literals

from mongoengine import QuerySet, DoesNotExist
from gym_bot_app.utils import get_week_days


class ExtendedQuerySet(QuerySet):
    def get(self, *q_objs, **query):
        try:
            if 'id' in query:
                query['id'] = unicode(query['id'])
            return super(ExtendedQuerySet, self).get(*q_objs, **query)
        except DoesNotExist:
            return None


class TraineeQuerySet(ExtendedQuerySet):
    def create(self, id, first_name):
        training_days = get_week_days()

        return super(TraineeQuerySet, self).create(id=unicode(id),
                                                   first_name=unicode(first_name),
                                                   training_days=training_days)


class GroupQuerySet(ExtendedQuerySet):
    pass