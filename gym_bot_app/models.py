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
                         EmbeddedDocumentField,
                         EmbeddedDocumentListField,
                         )

from gym_bot_app import DAYS_NAME
from gym_bot_app.query_sets import ExtendedQuerySet


DEFAULT_TRAINEE_CREATURE = 'שור עולם'


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


class PersonalConfigurations(EmbeddedDocument):
    creature = StringField(default=DEFAULT_TRAINEE_CREATURE)


class Trainee(Document):
    id = StringField(required=True, primary_key=True)
    first_name = StringField(required=True)
    training_days = EmbeddedDocumentListField(Day)
    personal_configurations = EmbeddedDocumentField(PersonalConfigurations,
                                                    default=PersonalConfigurations)

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

    @staticmethod
    def _calculate_training_percentage(num_of_trained_days, num_missed_training_days):
        """Calculate the training percentage based on the number of trained days.

        Args:
             num_of_trained_days(int): number of days the trainee trained.
             num_missed_training_days(int): number of days trainee commit to workout but did not.

        Returns:
            int. training percentage.
        """
        if (num_of_trained_days + num_missed_training_days) > 0:
            training_percentage = (100.0 / (num_of_trained_days + num_missed_training_days) * num_of_trained_days)
            return int(round(training_percentage))
        else:
            return 0

    @staticmethod
    def _calculate_average_training_days_per_week(trained_days):
        """Calculate the average training days per week.

        Args:
             trained_days(list<TrainingDayInfo>): all training days info when trainee did workout.

        Returns:
            float. average training days per week.
        """
        today = datetime.today()
        first_day_of_current_week = today - timedelta(days=today.weekday())
        trained_days_without_last_week = trained_days.filter(date__lt=first_day_of_current_week)
        first_trained_day = trained_days_without_last_week.first()
        if first_trained_day:
            first_day_of_week = first_trained_day.date - timedelta(days=first_trained_day.date.weekday())
            num_of_trained_days_per_week = [0]
            for trained_day in trained_days_without_last_week:
                if (trained_day.date - first_day_of_week).days >= 7:  # Start new week.
                    first_day_of_week = trained_day.date - timedelta(days=trained_day.date.weekday())
                    num_of_trained_days_per_week.append(0)

                # Increase number of trained days of the current week.
                num_of_trained_days_per_week[-1] += 1

            num_of_weeks_since_started_to_train = float((first_day_of_current_week - first_trained_day.date).days) / 7
            return float(sum(num_of_trained_days_per_week)) / round(num_of_weeks_since_started_to_train)
        else:
            return 0.

    def get_training_statistics(self):
        """Trainee training statistics.

        Calculate training statistics based on the TrainingDaysInfo of the trainee.

        Returns.
            int. number of days trainee went to the gym.
            int. number of days trainee did not go to the gym although it marked as training day.
            int. percentage of actually going to the gym vs missing days.
            float. average number of training days per week.
        """
        training_days_info = TrainingDayInfo.objects.filter(trainee=self.pk).order_by('date')
        trained_days = training_days_info.filter(trained=True)
        trained_days_count = trained_days.count()
        missed_training_days_count = training_days_info.filter(trained=False).count()
        training_percentage = self._calculate_training_percentage(num_of_trained_days=trained_days_count,
                                                                  num_missed_training_days=missed_training_days_count)
        average_training_days_per_week = self._calculate_average_training_days_per_week(trained_days=trained_days)

        return (trained_days_count,
                missed_training_days_count,
                training_percentage,
                average_training_days_per_week)

    @property
    def groups(self):
        return Group.objects.filter(trainees__contains=self)

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
        def create(self, id, trainees=None):
            if not trainees:
                trainees = []

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


class Admin(Document):
    id = StringField(required=True, primary_key=True)

    class AdminQuerySet(ExtendedQuerySet):
        def create(self, id):
            return super(Admin.AdminQuerySet, self).create(id=unicode(id))

        def is_admin(self, id):
            return bool(self.get(id=id))

    meta = {
        'queryset_class': AdminQuerySet,
    }

    def __repr__(self):
        return '<Admin {id}>'.format(id=self.id)

    def __str__(self):
        return repr(self)

    def __unicode__(self):
        return repr(self)
