import math
from datetime import datetime, timedelta
from calendar import monthrange

from mongoengine import (
    Document,
    IntField,
    ListField,
    FloatField,
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


MAX_EXP = 2147483648
LEVELS = {level_number: math.ceil((level_number - 1) * 3.5)
          for level_number in range(1, 200)}


class Day(EmbeddedDocument):
    name = StringField(required=True, max_length=64)
    selected = BooleanField(default=False)

    @classmethod
    def get_week_days(cls):
        return [cls(name=day_name) for day_name in DAYS_NAME]

    def __repr__(self):
        return '<Day {day_name} {selected}>'.format(day_name=self.name,
                                                    selected='selected' if self.selected
                                                             else 'not selected')

    def __str__(self):
        return repr(self)
    

class Level(EmbeddedDocument):
    number = IntField(default=1)
    exp = IntField(default=0)

    def gain_exp(self, exp):
        """Add EXP to the level.

        Args:
            exp (int): amount of gained EXP.

        Returns:
            bool. whether if leveled up by the gained exp or not.

        """
        self.exp += exp

        leveled_up = False  # Whether leveled up at least once after by the gained exp.
        should_level_up = True
        while should_level_up:
            should_level_up = self._should_level_up()

            if should_level_up:
                self._level_up()
                leveled_up = True

        return leveled_up

    def _level_up(self):
        self.exp -= self.required_exp_for_next_level  # Save the extra exp for the next level.
        self.number += 1

    def _should_level_up(self):
        return self.exp >= self.required_exp_for_next_level

    @property
    def required_exp_for_next_level(self):
        return LEVELS.get(self.number + 1, MAX_EXP)

    def __repr__(self):
        return '<Level {number} ({exp}/{next_level_exp})>'.format(
            number=self.number,
            exp=int(self.exp),
            next_level_exp=int(self.required_exp_for_next_level)
        )

    def __str__(self):
        return repr(self)


class PersonalConfigurations(EmbeddedDocument):
    creature = StringField(default=DEFAULT_TRAINEE_CREATURE)


class EXPEvent(Document):
    multiplier = FloatField()
    start_time = DateTimeField()
    end_time = DateTimeField()

    class EXPEventQuerySet(ExtendedQuerySet):
        def get_current_exp_events(self):
            now = datetime.now()

            return self.filter(start_time__lte=now, end_time__gte=now)

    meta = {
        'queryset_class': EXPEventQuerySet,
    }

    def __repr__(self):
        return '<EXPEvent {multiplier}x from {start_time} to {end_time}>'.format(
            multiplier=self.multiplier,
            start_time=self.start_time,
            end_time=self.end_time
        )

    def __str__(self):
        return repr(self)


class Trainee(Document):
    id = StringField(required=True, primary_key=True)
    first_name = StringField(required=True)
    training_days = EmbeddedDocumentListField(Day)
    level = EmbeddedDocumentField(Level, default=Level)
    personal_configurations = EmbeddedDocumentField(PersonalConfigurations,
                                                    default=PersonalConfigurations)

    class TraineeQuerySet(ExtendedQuerySet):
        def create(self, id, first_name):
            training_days = Day.get_week_days()

            return super(Trainee.TraineeQuerySet, self).create(id=str(id),
                                                               first_name=first_name,
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

    def get_mention_string(self):
        """Create telegram-style user mention string.

        Note: When using this you need to set the 'parse_mode' of the
            'send_message' function to 'markdown' mode.
        
        Returns:
            str. A telegram-style user mention.
        """
        return f"[@{self.first_name}](tg://user?id={self.id})"

    def add_training_info(self, training_date, trained):
        """Add training info to trainee.

        Args:
            training_date(datetime.date | datetime.datetime): date of the training info.
            trained(bool): whether trainee trained or not.

        Returns:
            tuple.
                TrainingDayInfo. instance of the created training day info.
                bool. whether trainee leveled up or not.

        Raises:
            RuntimeError. in case trainee already have training day info in the given date.

        """
        if self.get_training_info(training_date=training_date):
            raise RuntimeError('Already created training day info for today.')

        leveled_up = False
        gained_exp = 0
        if trained:
            gained_exp = 2

            exp_events = EXPEvent.objects.get_current_exp_events()

            for exp_event in exp_events:
                gained_exp *= exp_event.multiplier

            leveled_up = self.level.gain_exp(exp=gained_exp)
            self.save()

        training_day_info = TrainingDayInfo.objects.create(
            trainee=self.pk,
            date=training_date,
            trained=trained,
            gained_exp=gained_exp
        )
        return training_day_info, leveled_up

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

            num_of_weeks_since_started_to_train = round(float((first_day_of_current_week - first_trained_day.date).days) / 7)
            if num_of_weeks_since_started_to_train == 0:  # It's the first week of training.
                return sum(num_of_trained_days_per_week)
            else:
                return float(sum(num_of_trained_days_per_week)) / num_of_weeks_since_started_to_train
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

    def calculate_average_training_days_for_this_month(self, month):
        """Calculate the average training days for this month.

        Args:
            month(int): month (1-12) which you want to calculate the average training.

        Returns.
            int. number of days trained days in this month.
            int. number of days in this month.
            float. average training for this month.
        """
        year = datetime.now().year
        days_in_month = monthrange(year, month)[1]
        training_days_info = TrainingDayInfo.objects.filter(trainee=self.pk)
        trained_days_count = len(list(filter(
            lambda training: training.date >= datetime(year=year, month=month, day=1) and training.date <= datetime(year=year, month=month, day=days_in_month), 
          training_days_info)))
        if datetime.now().month == month:
            days_in_month = datetime.now().day
        average = trained_days_count / days_in_month
        return (trained_days_count,
                days_in_month,
                average)

    @property
    def groups(self):
        return Group.objects.filter(is_deleted=False, trainees__contains=self)

    def __repr__(self):
        return '<Trainee {id} {first_name}>'.format(id=self.id,
                                                    first_name=self.first_name)

    def __str__(self):
        return repr(self)


class TrainingDayInfo(Document):
    trainee = LazyReferenceField(document_type=Trainee)
    date = DateTimeField(default=datetime.now)
    trained = BooleanField()
    gained_exp = IntField(default=0)

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


class Group(Document):
    id = StringField(required=True, primary_key=True)
    trainees = ListField(CachedReferenceField(Trainee, auto_sync=True))
    level = EmbeddedDocumentField(Level, default=Level)
    is_deleted = BooleanField(default=False)

    class GroupQuerySet(ExtendedQuerySet):
        def create(self, id, trainees=None):
            if not trainees:
                trainees = []

            return super(Group.GroupQuerySet, self).create(id=str(id),
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

    def delete(self, *args, **kwargs):
        self.is_deleted = True
        self.save()


class Admin(Document):
    id = StringField(required=True, primary_key=True)

    class AdminQuerySet(ExtendedQuerySet):
        def create(self, id):
            return super(Admin.AdminQuerySet, self).create(id=str(id))

        def is_admin(self, id):
            return bool(self.get(id=id))

    meta = {
        'queryset_class': AdminQuerySet,
    }

    def __repr__(self):
        return '<Admin {id}>'.format(id=self.id)

    def __str__(self):
        return repr(self)
