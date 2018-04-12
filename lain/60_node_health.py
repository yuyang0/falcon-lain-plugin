#!/usr/bin/env python3
# -*- coding:utf-8 -*-

"""

"""
from __future__ import print_function, division, absolute_import

from subprocess import Popen, PIPE
import json
import time
import socket
import requests


def check_systemd(service):
    p = Popen(['systemctl', 'show', service], stdout=PIPE, stderr=PIPE)
    output, err = p.communicate()
    if p.returncode != 0:
        return False
    for line in output.split('\n'):
        if line.startswith('ActiveState=active'):
            return True
    return False


class NodeHealth(object):
    CHECK_LIST = ['docker', 'swarm_agent', 'lainlet', 'networkd', 'rebellion']

    _timeout = 5

    _endpoint = "lain"
    _host = socket.gethostname()
    _step = 60

    def __init__(self):
        self._result = []

    def run(self):
        self._result = []
        for item in self.CHECK_LIST:
            self.check(item)
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

    def check(self, item):
        try:
            return getattr(self, "check_%s" % item)()
        except:
            return False

    def check_etcd(self):
        url = "http://etcd.lain:4001/health"
        try:
            resp = requests.get(url, timeout=5)
            data = resp.json()
            is_alive = 1 if data.get('health') == "true" else 0
        except Exception:
            is_alive = 0
        self._append_result("lain.node.etcd.health",
                            self._endpoint, is_alive, self._step)

    def check_docker(self):
        url = "http://docker.lain:2375/info"
        start_at = time.time()
        try:
            resp = requests.get(url, timeout=self._timeout)
            docker_info_time = time.time() - start_at
            is_alive = 1 if resp.status_code == 200 else 0
        except Exception:
            is_alive = 0
            # use a very big time when failed to get info
            docker_info_time = 1000
        self._append_result("lain.node.docker.health",
                            self._endpoint, is_alive, self._step)
        self._append_result("lain.node.docker.latency",
                            self._endpoint, docker_info_time, self._step)

    def check_swarm_agent(self):
        is_alive = 1 if check_systemd('swarm-agent.service') else 0
        self._append_result("lain.node.swarm_agent.health",
                            self._endpoint, is_alive, self._step)

    def check_lainlet(self):
        is_alive = 1 if check_systemd('lainlet.service') else 0
        self._append_result("lain.node.lainlet.health",
                            self._endpoint, is_alive, self._step)

    def check_networkd(self):
        is_alive = 1 if check_systemd('networkd.service') else 0
        self._append_result("lain.node.networkd.health",
                            self._endpoint, is_alive, self._step)

    def check_rebellion(self):
        url = "http://docker.lain:2375"
        try:
            params = {"filters": '{"name": ["rebellion.service"]}'}
            containers = requests.get(
                "{}/containers/json".format(url),
                params=params,
                timeout=self._timeout).json()

            self._append_result("lain.node.rebellion.health",
                                self._endpoint, len(containers), self._step)
        except Exception as e:
            pass


if __name__ == "__main__":
    checker = NodeHealth()
    checker.run()
