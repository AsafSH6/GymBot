# encoding: utf-8
from __future__ import unicode_literals

from mongoengine import QuerySet, DoesNotExist
from models import Day


class ExtendedQuerySet(QuerySet):
    def get(self, *q_objs, **query):
        try:
            if 'id' in query:
                query['id'] = unicode(query['id'])
            return super(ExtendedQuerySet, self).get(*q_objs, **query)
        except DoesNotExist:
            return None


class TraineeQuerySet(ExtendedQuerySet):
    def create(self, trainee_id, first_name):
        training_days = Day.get_week_days()

        return super(TraineeQuerySet, self).create(trainee_id=unicode(trainee_id),
                                                   first_name=first_name,
                                                   training_days=training_days)
