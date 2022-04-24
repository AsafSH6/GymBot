import datetime
import logging
import os

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
                                  AllTrainingTraineesCommand)

from gym_bot_app.tasks import (GoToGymTask,
                               WentToGymTask,
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
    tasks = {
        task.__class__: task
        for task in tasks
    }

    """ Commands """
    AdminCommand(tasks=tasks, updater=updater, logger=logger).start()
    MyDaysCommand(tasks=tasks, updater=updater, logger=logger).start()
    TrainedCommand(tasks=tasks, updater=updater, logger=logger).start()
    RankingCommand(tasks=tasks, updater=updater, logger=logger).start()
    SelectDaysCommand(tasks=tasks, updater=updater, logger=logger).start()
    SetCreatureCommand(tasks=tasks, updater=updater, logger=logger).start()
    MyStatisticsCommand(tasks=tasks, updater=updater, logger=logger).start()
    BotStatisticsCommand(tasks=tasks, updater=updater, logger=logger).start()
    MotivationQuotesCommand(tasks=tasks, updater=updater, logger=logger).start()
    AllTrainingTraineesCommand(tasks=tasks, updater=updater, logger=logger).start(command_name='all_the_botim')

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
