from typing import TypedDict

from gym_bot_app.tasks.task import Task
from gym_bot_app.tasks.go_to_gym import GoToGymTask
from gym_bot_app.tasks.went_to_gym import WentToGymTask
from gym_bot_app.tasks.new_week_select_days import NewWeekSelectDaysTask
from gym_bot_app.tasks.did_not_train_updater import DidNotTrainUpdaterTask


class TaskTypeToInstance(TypedDict):
    GoToGymTask: GoToGymTask
    WentToGymTask: WentToGymTask
    NewWeekSelectDaysTask: NewWeekSelectDaysTask
    DidNotTrainUpdaterTask: DidNotTrainUpdaterTask
