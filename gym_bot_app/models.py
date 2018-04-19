# encoding: utf-8
from __future__ import unicode_literals

from datetime import datetime, timedelta

from mongoengine import (Document,
                         ListField,
                         StringField,
                         BooleanField,
                         DateTimeField,
                         EmbeddedDocument,
                         LazyReferenceField,
                         CachedReferenceField,
                         EmbeddedDocumentListField,
                         )

from gym_bot_app import DAYS_NAME
from gym_bot_app.query_sets import ExtendedQuerySet


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

    class TraineeQuerySet(ExtendedQuerySet):
        def create(self, id, first_name):
            training_days = Day.get_week_days()

            return super(Trainee.TraineeQuerySet, self).create(id=unicode(id),
                                                               first_name=unicode(first_name),
                                                               training_days=training_days)

    meta = {
        'queryset_class': TraineeQuerySet,
    }

    def unselect_all_days(self):
        for day in self.training_days:
            day.selected = False

        self.save()

    def is_training_today(self):
        today = datetime.now().strftime('%A')
        return self.is_training_in_day(day_name=today)

    def is_training_in_day(self, day_name):
        return self.training_days.get(name=day_name).selected

    def add_training_info(self, training_date, trained):
        """Add training info to trainee.

        Args:
            training_date(datetime.date | datetime.datetime): date of the training info.
            trained(bool): whether trainee trained or not.

        Returns:
            TrainingDayInfo. instance of the created training day info.

        Raises:
            RuntimeError. in case trainee already have training day info in the given date.

        """
        if self.get_training_info(training_date=training_date):
            raise RuntimeError('Already created training day info for today.')

        return TrainingDayInfo.objects.create(trainee=self.pk,
                                              date=training_date,
                                              trained=trained)

    def get_training_info(self, training_date):
        """Check trainee training info of given date.
        
        Args:
            training_date(datetime.date | datetime.datetime): date of requested training date.

        Returns:
            list. all TrainingDayInfo of requested training date.

        """
        next_day = training_date + timedelta(days=1)
        return TrainingDayInfo.objects.filter(trainee=self.pk,
                                              date__gte=training_date,
                                              date__lt=next_day)

    def __repr__(self):
        return '<Trainee {id} {first_name}>'.format(id=self.id,
                                                    first_name=self.first_name)

    def __str__(self):
        return repr(self)

    def __unicode__(self):
        return repr(self)


class TrainingDayInfo(Document):
    trainee = LazyReferenceField(document_type=Trainee)
    date = DateTimeField(default=datetime.now)
    trained = BooleanField()

    meta = {
        'indexes': [('trainee', '-date')],
        'index_background': True,
    }

    def __repr__(self):
        return '<TrainingDayInfo trainee {trainee_pk} {trained} {date}>'.format(trainee_pk=self.trainee.pk,
                                                                                trained='trained' if self.trained
                                                                                        else 'did not train',
                                                                                date=self.date.strftime('%d-%m-%Y %H:%M:%S'))

    def __str__(self):
        return repr(self)

    def __unicode__(self):
        return repr(self)


class Group(Document):
    id = StringField(required=True, primary_key=True)
    trainees = ListField(CachedReferenceField(Trainee, auto_sync=True))

    class GroupQuerySet(ExtendedQuerySet):
        def create(self, id, trainees=[]):
            return super(Group.GroupQuerySet, self).create(id=unicode(id),
                                                           trainees=trainees)

    meta = {
        'queryset_class': GroupQuerySet,
    }

    def add_trainee(self, new_trainee):
        self.update(push__trainees=new_trainee)
        return self

    def get_trainees_of_today(self):
        today = datetime.now().strftime('%A')
        return self.get_trainees_in_day(today)

    def get_trainees_in_day(self, day_name):
        return [trainee for trainee in self.trainees if trainee.is_training_in_day(day_name)]

    def __repr__(self):
        return '<Group {id}>'.format(id=self.id)

    def __str__(self):
        return repr(self)

    def __unicode__(self):
        return repr(self)

    def __iter__(self):
        return iter(self.trainees)
