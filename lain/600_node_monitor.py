# -*- coding: utf-8 -*-

import requests
import time
import json
import socket


class NodeMonitorPlugin(object):
    _timeout = 5

    _endpoint = "lain"
    _host = socket.gethostname()
    _step = 600

    def __init__(self):
        self._result = []

    def run(self):
        self._result = []
        self.read_docker_used_cpu_cores()
        print(json.dumps(self._result))

    def _append_result(self, metric, endpoint, val, step):
        data = {
            'Metric': metric,
            'Endpoint': endpoint,
            'Timestamp': int(time.time()),
            'Step': step,
            'Value': val,
            'CounterType': "GAUGE",
            'TAGS': "host=%s" % self._host,
        }
        self._result.append(data)

    def read_docker_used_cpu_cores(self):
        '''
        Unit: CPU Cores
        '''
        url_prefix = "http://docker.lain:2375"
        try:
            containers = requests.get(
                "{}/containers/json".format(url_prefix),
                timeout=self._timeout).json()
            docker_used_cpu_cores = 0
            for container in containers:
                stats = requests.get(
                    "{}/containers/{}/stats?stream=false".format(
                        self.DOCKER_URL_PREFIX, container["Id"]),
                    timeout=self._timeout).json()
                docker_used_cpu_cores += self.__calculate_cpu_cores(stats)
            self._append_result("lain.node.docker.used_cpu_cores",
                                self._endpoint, docker_used_cpu_cores, self._step)
        except Exception:
            pass

    def __calculate_cpu_cores(self, stats):
        '''
        Unit: CPU Cores
        '''
        cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats[
            "precpu_stats"]["cpu_usage"]["total_usage"]
        system_delta = stats["cpu_stats"]["system_cpu_usage"] - stats[
            "precpu_stats"]["system_cpu_usage"]
        if cpu_delta > 0 and system_delta > 0:
            return (float(cpu_delta) / system_delta
                    ) * len(stats["cpu_stats"]["cpu_usage"]["percpu_usage"])

        return 0


if __name__ == "__main__":
    node_monitor = NodeMonitorPlugin()
    node_monitor.run()
