import datetime
import logging
import redis
import json
from collections.abc import Callable

from runners_manager.runner.Runner import Runner
from runners_manager.runner.RunnerFactory import RunnerFactory
from runners_manager.runner.VmType import VmType

logger = logging.getLogger("runner_manager")


class RunnerManager(object):
    """
    This object create, delete and update runners infos bout VM and github runner
    We save every infos updated on the redis database
    This class is a tool and is here to join Github and local data
    """
    redis: redis.Redis
    vm_type: VmType
    runners: dict[str, Runner]
    factory: RunnerFactory

    def __init__(self, vm_type: VmType, factory: RunnerFactory, redis: redis.Redis):
        self.redis = redis
        self.vm_type = vm_type
        self.factory = factory
        self.runners = {}
        self._get_runners()

    def _redis_key_name(self):
        """
        Define the redis key name for this instance
        :return:
        """
        return f'managers:{"-".join(self.vm_type.tags)}'

    def _get_runners(self):
        """
        Build runners from redis
        :return:
        """
        value = self.redis.get(self._redis_key_name())
        if value is None:
            self.runners = {}
        else:
            self.runners = dict([(k, Runner.fromJson(v)) for k, v in json.loads(value).items()])

    def _save_runners(self):
        """
        Save runners json data in redis
        :return:
        """
        d = dict([(k, v.toJson()) for k, v in self.runners.items()])
        self.redis.set(self._redis_key_name(), json.dumps(d))

    def update(self, github_runners: list[dict]):
        """
        Update internal runners info from github.com
        :param github_runners:
        :return:
        """
        self._get_runners()

        # Remove runners not listed on github
        github_r_names = [r['name'] for r in github_runners]
        runners_to_deletes = [r for r in self.runners.keys() if r not in github_r_names]
        for name in runners_to_deletes:
            self.delete_runner(self.runners[name])

        # Update status of each runner
        for elem in github_runners:
            if elem['name'] in self.runners:
                runner = self.runners[elem['name']]
                runner.update_from_github(elem)

        self._save_runners()

    def create_runner(self):
        runner = self.factory.create_runner(self.vm_type)
        runner.update_status('creating')
        self.runners[runner.name] = runner
        self._save_runners()

    def delete_runner(self, runner: Runner):
        runner.update_status('deleting')
        self.factory.delete_runner(runner)
        del self.runners[runner.name]
        del runner
        self._save_runners()

    def respawn_runner(self, runner: Runner):
        runner.update_status('respawning')
        self.factory.respawn_replace(runner)
        self._save_runners()

    def runners_not_used_for(self, duration: datetime.timedelta):
        return self.filter_runners(lambda runner: runner.status == 'online'
                                   and not runner.has_run
                                   and runner.time_online > duration)

    def filter_runners(self, cond: Callable[[Runner], bool]):
        """
        Return a list of runner matching the condition function
        :param cond:
        :return:
        """
        return list(filter(
            lambda e: e.vm_type.tags == self.vm_type.tags and cond(e),
            self.runners.values()
        ))

    def min_runner_number(self):
        return self.vm_type.quantity['min']

    def max_runner_number(self):
        return self.vm_type.quantity['max']
