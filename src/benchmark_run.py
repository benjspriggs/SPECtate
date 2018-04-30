"""
This module replaces `run.sh`.
"""

from multiprocessing import Pool
from uuid import uuid4
import logging
import configparser

from src.task_runner import TaskRunner

log = logging.getLogger(__name__)


class InvalidRunConfigurationException(Exception):
    def __init__(self, msg="Run was invalid"):
        self.msg = msg

    def __str__(self):
        return self.msg


def do(task):
    """
    Runs a given task synchronously.
    This needs to be pickled for Pool.map, which is why it's hanging out here.
    """
    log.debug("starting task {}".format(task))
    task.run()
    log.debug("finished task {}".format(task))


class JvmRunOptions:
    def __init__(self, val=None):
        if isinstance(val, str):
            self.__dict__ = {
                "path": val,
                "options": [],
            }
        elif isinstance(val, list):
            self.__dict__ = {
                "path": val[0],
                "options": val[1:],
            }
        elif isinstance(val, dict):
            if "path" not in val:
                raise Exception("'path' not specified for JvmRunOptions")
            if not isinstance(val["path"], str):
                raise Exception("'path' must be a string")
            if "options" not in val:
                val["options"] = []
            elif not isinstance(val["options"], list):
                raise Exception("'path' must be a string")

            self.__dict__ = val
        elif val is None:
            self.__dict__ = {
                "path": "java",
                "options": []
            }
        else:
            raise Exception(
                "unrecognized type given to JvmRunOptions: {}".format(type(val)))

    def __getitem__(self, name):
        return self.__dict__.__getitem__(name)

    def __getattr__(self, name):
        return self.__dict__.__getitem__(name)


SpecJBBComponentTypes = [
    "backend",
    "txinjector",
    "composite",
    "multi",
    "distributed",
]


class SpecJBBComponentOptions:
    def __init__(self, init, count=1):
        if isinstance(init, str):
            if init not in SpecJBBComponentTypes:
                raise Exception(
                    "Type '{}' is not a valid SpecJBB component type".format(init))
        elif not isinstance(init, dict):
            raise Exception(
                "Unrecognized type given to SpecJBBComponentOptions: {}".format(type(init)))

        if isinstance(init, dict):
            if "type" not in init:
                raise Exception(
                    "'type' not specified in SpecJBBComponentOptions")
            if "count" not in init:
                init["count"] = count
            if "options" not in init:
                init["options"] = []
            if "jvm_opts" not in init:
                init["jvm_opts"] = []

            self.__dict__ = init
        else:
            self.__dict__ = {
                "type": init,
                "count": count,
                "options": [],
                "jvm_opts": []
            }

    def __getitem__(self, name):
        return self.__dict__.__getitem__(name)

    def __getattr__(self, name):
        return self.__dict__.__getitem__(name)

class SpecJBBRun:
    """
    Does a run!
    """

    def __init__(self,
                 controller=None,
                 backends=None,
                 injectors=None,
                 java=None,
                 jar=None,
                 props={},
                 props_file='specjbb2015.props'):
        if None in [java, jar] or not isinstance(jar, str):
            raise InvalidRunConfigurationException

        self.jar = jar
        self.props = props
        self.props_file = props_file
        self.run_id = uuid4()
        self.log = logging.LoggerAdapter(log, {'run_id': self.run_id})

        self.__set_java__(java)
        self.__set_topology__(controller, backends, injectors)

    def __set_java__(self, java):
        """
        Sets the internal java dictionary based on what's passed into __init__.
        """
        if isinstance(java, str):
            self.java = {
                "path": java,
                "options": []
            }
        elif isinstance(java, list):
            self.java = {
                "path": java[0],
                "options": java[1:],
            }
        elif isinstance(java, dict):
            self.java = java
        else:
            raise InvalidRunConfigurationException(
                "'java' was not a string, list, or dictionary")

    def __set_topology__(self, controller, backends, injectors):
        """
        Sets the topology dictionaries based on what's passed into __init__.
        Will also raise exceptions if we don't get what we're expecting.
        """
        if controller is None and backends is None and injectors is None:
            raise InvalidRunConfigurationException("no topology specified")
        if not isinstance(controller, dict):
            raise InvalidRunConfigurationException(
                "'controller' was not a dict")
        if "type" not in controller:
            raise InvalidRunConfigurationException(
                "'type' wasn't specified in 'controller'")

        if controller is None:
            self.controller = {
                "type": "composite",
                "options": [],
                "jvm_opts": [],
            }
        else:
            self.controller = controller

            # TODO: ensure the right SPECjbb run arguments are added to "options"

        if isinstance(backends, int):
            self.backends = {
                "count": backends,
                "type": "backend",
                "options": [],
                "jvm_opts": [],
            }
        elif isinstance(backends, dict):
            self.backends = backends

            # TODO: ensure the right SPECjbb run arguments are added to "options"
        elif backends is None:
            self.backends = {
                "count": 1,
                "type": "backend",
                "options": [],
                "jvm_opts": [],
            }
        else:
            raise InvalidRunConfigurationException(
                "'backends' was not an integer or dict")

        if isinstance(injectors, int):
            self.injectors = {
                "count": injectors,
                "type": "txinjector",
                "options": [],
                "jvm_opts": [],
            }
        elif isinstance(injectors, dict):
            self.injectors = injectors

            # TODO: ensure the right SPECjbb run arguments are added to "options"
        elif injectors is None:
            self.injectors = {
                "count": 1,
                "type": "txinjector",
                "options": [],
                "jvm_opts": [],
            }
        else:
            raise InvalidRunConfigurationException(
                "'injectors' was not an integer or dict")

    def _generate_tasks(self):
        if self.controller["type"] is "composite":
            return

        self.log.info(
            "generating {} groups, each with {} transaction injectors"
                .format(self.backends["count"], self.injectors["count"]))

        for _ in range(self.backends["count"]):
            group_id = uuid4()
            backend_jvm_id = uuid4()
            self.log.debug("constructing group {}".format(group_id))
            yield TaskRunner(*self.backend_run_args(),
                             '-G={}'.format(group_id),
                             '-J={}'.format(backend_jvm_id))

            self.log.debug(
                "constructing injectors for group {}".format(group_id))

            for _ in range(self.injectors["count"]):
                ti_jvm_id = uuid4()
                self.log.debug(
                    "preparing injector in group {} with jvmid={}".format(group_id, ti_jvm_id))
                yield TaskRunner(*self.injector_run_args(),
                                 '-G={}'.format(group_id),
                                 '-J={}'.format(ti_jvm_id))

    def run(self):
        # write props file (or ensure it exists)
        with open(self.props_file, 'w+') as props_file:
            c = configparser.ConfigParser()
            c.read_dict({'SPECtate': self.props})
            c.write(props_file)
        # setup jvms
        # we first need to setup the controller
        c = TaskRunner(*self.controller_run_args())
        self.dump()

        if self.controller["type"] is "composite":
            self.log.info("begin benchmark")
            c.run()
            self.log.info("done")
            return

        c.start()

        tasks = [task for task in self._generate_tasks()]
        pool = Pool(processes=len(tasks))

        self.dump()

        # run benchmark
        self.log.info("begin benchmark")

        pool.map(do, tasks)
        c.stop()
        self.log.info("done")

    def dump(self, level=logging.DEBUG):
        """
        Dumps info about this currently configured run.
        """

        self.log.log(level, vars(self))

    def _full_options(self, options_dict):
        """
        Returns a list of arguments, formatted for the specific JVM invocation.
        """
        self.log.debug(
            "full options being generated from: {}".format(options_dict))

        java = [self.java["path"], "-jar", self.jar] + \
            self.java["options"] + options_dict.get("jvm_opts", [])
        spec = ["-m", options_dict["type"].upper()] + \
            options_dict.get("options", []) + ["-p", self.props_file]

        self.log.debug("java: {}, spec: {}".format(java, spec))

        return java + spec

    def controller_run_args(self):
        return self._full_options(self.controller)

    def backend_run_args(self):
        return self._full_options(self.backends)

    def injector_run_args(self):
        return self._full_options(self.injectors)
