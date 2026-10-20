import math
import logging
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


logger = logging.getLogger(__name__)


DEFAULT_TRAINEE_CREATURE = 'שור עולם'


MAX_PERSONAL_MOTIVATION_LENGTH = 200


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

    @property
    def total_exp(self):
        """All the EXP gained to reach this level from level 1."""
        return sum(LEVELS.get(level_number, MAX_EXP) for level_number in range(2, self.number + 1)) + self.exp

    @classmethod
    def from_total_exp(cls, total_exp):
        """Create the level reached by gaining the given EXP from level 1."""
        level = cls()
        level.gain_exp(exp=total_exp)
        return level

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


class Season(EmbeddedDocument):
    """A finished season of a trainee, frozen when the trainee started a new one.

    Training history is never deleted, so the training days of a season are counted from
    TrainingDayInfo between started_at and ended_at. Only the level is kept here, since it
    is the one part of a season that is not derived from the history.

    """
    number = IntField(required=True)
    started_at = DateTimeField()  # None for the first season, which counts from the beginning.
    ended_at = DateTimeField(required=True)
    level = EmbeddedDocumentField(Level, default=Level)

    def __repr__(self):
        return '<Season {number} {level}>'.format(number=self.number, level=self.level)

    def __str__(self):
        return repr(self)


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
    season_number = IntField(default=1)
    season_started_at = DateTimeField()  # None for the first season, which counts from the beginning.
    past_seasons = EmbeddedDocumentListField(Season)

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
        if self.get_training_info(start_training_date=training_date):
            raise RuntimeError('Already created training day info for today.')

        leveled_up = False
        gained_exp = 0
        if trained:
            gained_exp = 2

            exp_events = EXPEvent.objects.get_current_exp_events()

            for exp_event in exp_events:
                gained_exp *= exp_event.multiplier

            past_season = self._get_past_season_of(training_date)
            if past_season is not None:
                # A late answer for a day of a season that already ended, e.g. answering the
                # went to gym question after the midnight a new season started at.
                past_season.level.gain_exp(exp=gained_exp)
            else:
                leveled_up = self.level.gain_exp(exp=gained_exp)
            self.save()

        training_day_info = TrainingDayInfo.objects.create(
            trainee=self.pk,
            date=training_date,
            trained=trained,
            gained_exp=gained_exp
        )
        return training_day_info, leveled_up

    def get_training_info(self, start_training_date, num_of_training_days=1):
        """Check trainee training info of given period.
        
        Args:
            start_training_date(datetime.date | datetime.datetime): date of requested training date.
            num_of_training_days(int): number of requested training date, default 1.

        Returns:
            list. all TrainingDayInfo of requested training date.

        """
        requested_days = start_training_date + timedelta(days=num_of_training_days)
        return TrainingDayInfo.objects.filter(trainee=self.pk,
                                              date__gte=start_training_date,
                                              date__lt=requested_days)

    def get_season_training_info(self):
        """All training info of the current season.

        Statistics are calculated from this so they start over with a new season. Checks of
        whether the trainee already answered about a given day must keep using
        get_training_info, otherwise the trainee could train twice on the day a season starts.

        Returns:
            QuerySet. TrainingDayInfo of the trainee since the current season started.

        """
        training_days_info = TrainingDayInfo.objects.filter(trainee=self.pk)
        if self.season_started_at is not None:
            training_days_info = training_days_info.filter(date__gte=self.season_started_at)

        return training_days_info

    def count_trained_days_in_past_season(self, season):
        """Count the days the trainee trained in the given past season.

        Args:
            season(Season): one of the trainee's past seasons.

        Returns:
            int. number of days trainee trained in the season.

        """
        trained_days = TrainingDayInfo.objects.filter(trainee=self.pk, trained=True, date__lt=season.ended_at)
        if season.started_at is not None:
            trained_days = trained_days.filter(date__gte=season.started_at)

        return trained_days.count()

    def _get_past_season_of(self, training_date):
        """Find the past season the given date belongs to.

        Args:
            training_date(datetime.date | datetime.datetime): date of the training info.

        Returns:
            Season | None. the past season of the date, None if it belongs to the current season.

        """
        training_date = datetime(year=training_date.year, month=training_date.month, day=training_date.day)
        if self.season_started_at is None or training_date >= self.season_started_at:
            return None

        return next((season for season in reversed(self.past_seasons)
                     if season.started_at is None or season.started_at <= training_date),
                    None)

    def can_start_season_at(self, started_at):
        """Check whether a new season can start at the given time.

        It cannot if the current season started at that time or later: the trainee joined
        two votes that closed together, or an older vote is closing late, after the bot was
        down. Either way the trainee already started over at least as recently.

        Args:
            started_at(datetime.datetime): when the new season would start.

        Returns:
            bool. whether a new season can start at the given time.

        """
        return self.season_started_at is None or self.season_started_at < started_at

    def count_gained_exp_since(self, date):
        """Sum the EXP the trainee gained from trainings on the given date or after it.

        Args:
            date(datetime.datetime): first day to count.

        Returns:
            int. gained EXP.

        """
        return sum(training_day_info.gained_exp
                   for training_day_info in TrainingDayInfo.objects.filter(trainee=self.pk,
                                                                           trained=True,
                                                                           date__gte=date))

    def start_new_season(self, started_at):
        """Archive the current season and start a new one from level 1.

        Nothing is deleted: the training history stays, the statistics count from started_at
        on, and the finished season keeps its level for /my_statistics and for undo.

        Trainings on started_at or after it belong to the new season even if they were
        recorded before it actually started, e.g. when the bot was down at midnight, so
        their EXP moves from the archived level to the new one.

        Args:
            started_at(datetime.datetime): when the new season starts, should be a midnight.

        Returns:
            bool. whether a new season started, see can_start_season_at.

        """
        if not self.can_start_season_at(started_at):
            return False

        new_season_exp = self.count_gained_exp_since(started_at)
        previous_season_exp = self.level.total_exp - new_season_exp
        if previous_season_exp < 0:
            # Every training from started_at on was credited to the current level, so this
            # means the data is inconsistent.
            logger.warning('%s has %s EXP in total but gained %s since %s',
                           self, self.level.total_exp, new_season_exp, started_at)
            previous_season_exp = 0

        self.past_seasons.append(Season(number=self.season_number,
                                        started_at=self.season_started_at,
                                        ended_at=started_at,
                                        level=Level.from_total_exp(previous_season_exp)))
        self.season_number += 1
        self.season_started_at = started_at
        self.level = Level.from_total_exp(new_season_exp)
        self.save()

        return True

    def undo_season(self):
        """Go back to the previous season, keeping the EXP gained since the current one started.

        The current season started from level 1, so its level holds exactly the EXP gained
        since, and adding it to the archived level restores the trainee exactly.

        """
        previous_season = self.past_seasons.pop()
        self.level = Level.from_total_exp(previous_season.level.total_exp + self.level.total_exp)
        self.season_number = previous_season.number
        self.season_started_at = previous_season.started_at
        self.save()

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
        training_days_info = self.get_season_training_info().order_by('date')
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

    def calculate_statistics_training_days_for_this_month(self, month):
        """Calculate the statistics training days for the given month.

        Args:
            month(int): month (1-12) which you want to calculate the statistics training.

        Returns.
            int. number of days trained days in this month.
            int. number of days in this month.
            float. training percentage for this month.
        """
        date = datetime.now()
        year = date.year
        days_in_month = monthrange(year, month)[1]
        if date.month == month:
            days_in_month = date.day

        start_training_date = datetime(year=year, month=month, day=1)
        trained_days_count = self.get_season_training_info().filter(
            trained=True,
            date__gte=start_training_date,
            date__lt=start_training_date + timedelta(days=days_in_month)
        ).count()
        if trained_days_count == 0:
            training_percentage = 0
        else:
            training_percentage = round(trained_days_count / (days_in_month / 100), 1)

        return trained_days_count, days_in_month, training_percentage

    def calculate_statistics_training_days_for_this_year(self, selected_year):
        """Calculate the statistics training days for the given year.

        Args:
            year(int): year which you want to calculate the statistics training.

        Returns.
            int. number of days trained days in this year.
            int. number of days in this year.
            float. training percentage for this year.
        """
        today = datetime.now()
        start_of_year = datetime(year=selected_year, month=1, day=1)
        
        if today.year == selected_year:
            # If current year, only count days from Jan 1 to today
            days_in_year = (today - start_of_year).days + 1
        else:
            # For past years, calculate total days in the year using timedelta
            days_in_year = (datetime(year=selected_year + 1, month=1, day=1) - start_of_year).days

        trained_days_count = self.get_season_training_info().filter(
            trained=True,
            date__gte=start_of_year,
            date__lt=start_of_year + timedelta(days=days_in_year)
        ).count()
        if trained_days_count == 0:
            training_percentage = 0
        else:
            training_percentage = round(trained_days_count / (days_in_year / 100), 1)

        return trained_days_count, days_in_year, training_percentage

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


class FreshStartVote(Document):
    """Vote of a group to start a new season.

    Every trainee who joins the vote before it closes starts a new season from level 1,
    and the bot level of the group starts over too.

    Closing goes through CLOSING to DONE. Each step of it is recorded on the vote, so a
    closing interrupted by a crash stays CLOSING, is finished when the bot starts again,
    and never resets anything twice.

    """
    PENDING = 'pending'
    CLOSING = 'closing'
    DONE = 'done'
    CANCELLED = 'cancelled'
    UNDONE = 'undone'

    group = LazyReferenceField(document_type=Group, required=True)
    created_by = StringField()
    created_at = DateTimeField(default=datetime.now)
    executes_at = DateTimeField(required=True)
    message_id = IntField()
    participants = ListField(StringField())
    reset_trainees = ListField(StringField())  # Participants this vote started a new season for.
    status = StringField(choices=(PENDING, CLOSING, DONE, CANCELLED, UNDONE), default=PENDING)
    group_level = EmbeddedDocumentField(Level)  # Bot level of the group before the reset, for undo.
    group_level_reset = BooleanField(default=False)
    reminded = BooleanField(default=False)  # Whether the group was reminded the vote closes soon.

    class FreshStartVoteQuerySet(ExtendedQuerySet):
        def get_pending(self, group):
            return self.filter(group=group.pk, status=FreshStartVote.PENDING).first()

        def get_last_done(self, group):
            return self.filter(group=group.pk, status=FreshStartVote.DONE).order_by('-executes_at').first()

        def get_unfinished(self, group=None):
            votes = self.filter(status__in=(FreshStartVote.PENDING, FreshStartVote.CLOSING))
            return votes if group is None else votes.filter(group=group.pk)

    meta = {
        'queryset_class': FreshStartVoteQuerySet,
    }

    def add_participant(self, trainee):
        """Add the given trainee to the vote, if it is still open.

        Returns:
            bool. whether the vote was still open.

        """
        updated = FreshStartVote.objects.filter(id=self.id, status=self.PENDING).update_one(
            add_to_set__participants=trainee.id
        )
        self.reload()
        return bool(updated)

    def remove_participant(self, trainee):
        """Remove the given trainee from the vote, if it is still open.

        Returns:
            bool. whether the vote was still open.

        """
        updated = FreshStartVote.objects.filter(id=self.id, status=self.PENDING).update_one(
            pull__participants=trainee.id
        )
        self.reload()
        return bool(updated)

    def mark_reminded(self):
        """Mark the group as reminded that the vote closes soon, if the vote is still open.

        Returns:
            bool. True if the vote is still open and the group was not reminded yet, so the
                reminder should be sent now.

        """
        # Not reminded=False, which would not match a vote saved before the field existed.
        # Not reloaded after, which is one more DB call that could fail after the vote was
        # marked, losing the reminder.
        return bool(FreshStartVote.objects.filter(id=self.id, status=self.PENDING, reminded__ne=True).update_one(
            set__reminded=True
        ))

    def close(self):
        """Close the vote, so nobody can join or leave it anymore.

        A vote nobody joined is cancelled.

        Returns:
            bool. True if the vote was closed now or was left CLOSING by a crash, False if it
                was already done, cancelled or undone.

        """
        FreshStartVote.objects.filter(id=self.id, status=self.PENDING).update_one(set__status=self.CLOSING)
        self.reload()
        if self.status != self.CLOSING:
            return False

        if not self.participants:
            self.status = self.CANCELLED
            self.save()

        return True

    def cancel(self):
        """Cancel the vote if it is still open.

        Returns:
            bool. whether the vote was still open.

        """
        return bool(FreshStartVote.objects.filter(id=self.id, status=self.PENDING).update_one(
            set__status=self.CANCELLED
        ))

    def start_new_seasons(self):
        """Start a new season for the participants and reset the bot level of the group.

        Must be called on a closed vote. Steps that were already done, by a closing that
        crashed half way, are skipped.

        Returns:
            list. the trainees this vote started a new season for.

        """
        for trainee in Trainee.objects.filter(id__in=self.participants):
            if trainee.id not in self.reset_trainees:
                if not trainee.can_start_season_at(self.executes_at):
                    continue  # Already started over in another group's vote.

                # Recorded before the reset, so a crash right after it cannot lose the trainee.
                self.reset_trainees.append(trainee.id)
                self.save()

            trainee.start_new_season(started_at=self.executes_at)

        if not self.group_level_reset:
            group = Group.objects.get(id=self.group.pk)
            if self.group_level is None:
                self.group_level = Level(number=group.level.number, exp=group.level.exp)
                self.save()

            group.level = Level()
            group.save()
            self.group_level_reset = True
            self.save()

        self.status = self.DONE
        self.save()

        return list(Trainee.objects.filter(id__in=self.reset_trainees))

    def undo(self):
        """Undo the new seasons, keeping the EXP gained since they started.

        Trainees who already started another season since are left as they are.

        Returns:
            list. the trainees who went back to their previous season.

        """
        trainees = [trainee for trainee in Trainee.objects.filter(id__in=self.reset_trainees)
                    if trainee.season_started_at == self.executes_at]
        for trainee in trainees:
            trainee.undo_season()

        if self.group_level_reset:
            group = Group.objects.get(id=self.group.pk)
            group.level = Level.from_total_exp(self.group_level.total_exp + group.level.total_exp)
            group.save()

        self.status = self.UNDONE
        self.save()

        return trainees

    def __repr__(self):
        return '<FreshStartVote {group_id} {status} at {executes_at}>'.format(group_id=self.group.pk,
                                                                              status=self.status,
                                                                              executes_at=self.executes_at)

    def __str__(self):
        return repr(self)


class PersonalMotivationQuote(Document):
    """Motivation sentence of a trainee, added to the motivation quotes of one group.

    A trainee has at most one sentence in each group, setting another one replaces it.

    """
    group = LazyReferenceField(document_type=Group, required=True)
    trainee = LazyReferenceField(document_type=Trainee, required=True)
    text = StringField(required=True, max_length=MAX_PERSONAL_MOTIVATION_LENGTH)
    updated_at = DateTimeField(default=datetime.now)

    meta = {
        'indexes': [{'fields': ('group', 'trainee'), 'unique': True}],
        'index_background': True,
    }

    def __repr__(self):
        return '<PersonalMotivationQuote of trainee {trainee_pk} in group {group_pk}>'.format(
            trainee_pk=self.trainee.pk,
            group_pk=self.group.pk
        )

    def __str__(self):
        return repr(self)


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
