# encoding: utf-8
from __future__ import unicode_literals
from gym_bot_app.utils import (DAYS_NAME,
                               upper_first_letter)
from gym_bot_app.db.query_sets import (TraineeQuerySet,
                                       GroupQuerySet)
from mongoengine import (Document,
                         ListField,
                         StringField,
                         BooleanField,
                         EmbeddedDocument,
                         EmbeddedDocumentListField,
                         CachedReferenceField)


class Day(EmbeddedDocument):
    name = StringField(required=True, max_length=64)
    selected = BooleanField(default=False)

    @classmethod
    def get_week_days(cls):
        return [cls(day_name) for day_name in DAYS_NAME]

    def __repr__(self):
        return '<Day {day_name} {selected}>'.format(day_name=self.name,
                                                    selected='selected' if self.selected
                                                             else 'not selected')

    def __str__(self):
        return repr(self)

    def __unicode__(self):
        return repr(self)


class Trainee(Document):
    id = StringField(required=True, primary_key=True)
    first_name = StringField(required=True)
    training_days = EmbeddedDocumentListField(Day)

    meta = {'queryset_class': TraineeQuerySet}

    def __repr__(self):
        return '<Trainee {id} {first_name}>'.format(id=self.id,
                                                    first_name=self.first_name)

    def __str__(self):
        return repr(self)

    def __unicode__(self):
        return repr(self)


class Group(Document):
    id = StringField(required=True, primary_key=True)
    trainees = ListField(CachedReferenceField(Trainee, auto_sync=True))

    meta = {'queryset_class': GroupQuerySet}

    @classmethod
    def create(cls, group_id, trainees=[]):
        new_group = cls(id=unicode(group_id))
        new_group.trainees.extend(trainees)

        return new_group.save()

    def add_trainee(self, new_trainee):
        self.trainees.append(new_trainee)
        return self.save()

    def get_trainees_in_day(self, day_name):
        day_idx = DAYS_NAME.index(upper_first_letter(day_name))
        return [trainee for trainee in self.trainees if trainee.training_days[day_idx].selected]

    def __repr__(self):
        return '<Group {id} [{trainees}]>'.format(id=self.id,
                                                  trainees='{trainee},'.join(str(trainee) for trainee in self.trainees))

    def __str__(self):
        return repr(self)

    def __unicode__(self):
        return repr(self)