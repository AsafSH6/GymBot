import os
import logging

from telegram.ext import Updater

from gym_bot_app.commands import (AdminCommand,
                                  MyDaysCommand,
                                  TrainedCommand,
                                  RankingCommand,
                                  SelectDaysCommand,
                                  SetCreatureCommand,
                                  MyStatisticsCommand,
                                  BotStatisticsCommand,
                                  MotivationQuotesCommand,
                                  AllTrainingTraineesCommand,
                                  MonthRankingCommand)

from gym_bot_app.tasks import (GoToGymTask,
                               WentToGymTask,
                               TaskTypeToInstance,
                               NewWeekSelectDaysTask,
                               DidNotTrainUpdaterTask)


MSG_TIMEOUT = 20

logging.basicConfig(filename='logs/gymbot.log',
                    format='%(asctime)s %(levelname)s - [%(module)s:%(funcName)s:%(lineno)d] %(message)s',
                    datefmt='%d-%m-%Y:%H:%M:%S',
                    level=logging.INFO)


def run_gym_bot(token, logger):
    updater = Updater(token=token)

    """ Tasks """
    tasks = [
        GoToGymTask(updater=updater, logger=logger).start(),
        WentToGymTask(updater=updater, logger=logger).start(),
        NewWeekSelectDaysTask(updater=updater, logger=logger).start(),
        DidNotTrainUpdaterTask(updater=updater, logger=logger).start(),
    ]

    task_type_to_instance: TaskTypeToInstance = {
        task.__class__.__name__: task
        for task in tasks
    }

    """ Commands """
    AdminCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    MyDaysCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    TrainedCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    RankingCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    SelectDaysCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    SetCreatureCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    MonthRankingCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    MyStatisticsCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    BotStatisticsCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    MotivationQuotesCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    AllTrainingTraineesCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start(command_name='all_the_botim')

    updater.start_polling(timeout=MSG_TIMEOUT)
    updater.idle()


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        os.environ['BOT_TOKEN'] = os.environ['BOT_TOKEN_TEST']
        os.environ['MONGODB_URL_CON'] = os.environ['MONGODB_URL_CON_TEST']

    token = os.environ['BOT_TOKEN']
    db_con_string = os.environ['MONGODB_URL_CON']

    from mongoengine import connect
    connect(host=db_con_string)

    logger = logging.getLogger()
    logger.addHandler(logging.StreamHandler())

    run_gym_bot(token, logger)
