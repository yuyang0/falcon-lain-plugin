#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import urllib
import docker
import json
import time
import argparse
import socket


class AppCollector(object):
    COLLECT_LIST = ['cpu', 'memory', 'blkio', 'network']

    _timeout = 5

    _endpoint = "lain"
    _host = socket.gethostname()
    _step = 60

    def __init__(self, stats, info):
        self._result = []
        self.stats = stats
        self.info = info

    def run(self):
        self._result = []
        for item in self.COLLECT_LIST:
            self._collect(item)
            if len(self._result) > 0:
                print(json.dumps(self._result))

    def _append_result(self, metric, val, lain_info, counter_ty="GAUGE"):
        endpoint = lain_info["endpoint"]
        metric = lain_info["metric"] + "." + metric
        data = {
            'Metric': metric,
            'Endpoint': endpoint,
            'Timestamp': int(time.time()),
            'Step': self._step,
            'Value': val,
            'CounterType': counter_ty,
            'TAGS': "",
        }
        self._result.append(data)

    def _collect(self, item):
        try:
            return getattr(self, "_collect_%s_stats" % item)()
        except:
            return False

    def _collect_cpu_stats(self):
        # docker cpu stats is nanoseconds, plus 100 for percent, *100/1e9 =
        # /1e7
        stats = self.stats
        lain_info = self.info

        self._append_result("cpu.total", int(
            int(stats["cpu_stats"]["cpu_usage"]["total_usage"]) / 1e7), lain_info)
        self._append_result("cpu.user", int(
            int(stats["cpu_stats"]["cpu_usage"]["usage_in_usermode"]) / 1e7), lain_info)
        self._append_result("cpu.kernel", int(
            int(stats["cpu_stats"]["cpu_usage"]["usage_in_kernelmode"]) / 1e7), lain_info)

    def _collect_memory_stats(self):
        stats = self.stats
        lain_info = self.info

        usage = stats["memory_stats"]["usage"]
        self._append_result("memory.usage", usage, lain_info)

        stat_list = stats["memory_stats"]["stats"]
        if not stat_list:
            return
        for stat in stat_list:
            if stat.startswith("total_"):
                metric = "memory.%s" % (stat[6:])
                value = stat_list[stat]
                self._append_result(metric, value, lain_info)

    def _collect_blkio_stats(self):
        """
        "blkio_stats": {
            "io_merged_recursive": [],
            "io_queue_recursive": [],
            "io_service_bytes_recursive": [],
            "io_service_time_recursive": [],
            "io_serviced_recursive": [],
            "io_time_recursive": [],
            "io_wait_time_recursive": [],
            "sectors_recursive": []
        }
        """

        # blkio-io_service_bytes_recursive-253-0-READ
        BLKIO_KEY_FORMAT = 'blkio.%s-%s-%s-%s'

        stats = self.stats
        lain_info = self.info

        for stat, value in stats["blkio_stats"].iteritems():
            blk_stats = {}
            for item in value:
                key = BLKIO_KEY_FORMAT % (
                    stat, item['major'], item['minor'], item['op'])
                blk_stats[key] = item['value']

            for key, value in blk_stats.iteritems():
                self._append_result(
                    key, value, lain_info, "COUNTER")

    def _collect_network_stats(self):
        """
        "networks": {
            "rx_bytes": 0,
            "rx_dropped": 0,
            "rx_errors": 0,
            "rx_packets": 0,
            "tx_bytes": 0,
            "tx_dropped": 0,
            "tx_errors": 0,
            "tx_packets": 0
        },
        """
        stats = self.stats
        lain_info = self.info

        if "networks" not in stats:
            return
        for interface in stats["networks"]:
            for stat in stats["networks"][interface]:
                self._append_result("net.%s-%s" % (interface, stat),
                                    stats["networks"][interface][stat], lain_info, "COUNTER")


class Docker:
    BASE_URL = "unix://var/run/docker.sock"
    client = docker.Client(base_url=BASE_URL)

    @classmethod
    def get_stats(cls, container_id):
        st = cls.client.stats(container_id, decode=True)
        return st.next()

    @classmethod
    def get_inspect_env(cls, container_id):
        env_dict = {}
        envlist = cls.client.inspect_container(container_id)["Config"]["Env"]
        if envlist:
            for env in envlist:
                try:
                    key, value = env.strip().split("=")
                    env_dict[key] = value
                except ValueError:
                    continue
        return env_dict

    @classmethod
    def get_all_running_containers(cls):
        result = []
        for container in cls.client.containers():
            if container["Status"].startswith("Up"):
                result.append(container)
        return result


class Lainlet(object):

    def __init__(self, url, hostname):
        self.url = url
        self.hostname = hostname

    def get_containers(self):
        # app: DOMAIN.app.APPNAME.proc.PROCNAME.instance.NO.
        url = "%s/v2/containers?nodename=%s" % (self.url, self.hostname)
        r = urllib.urlopen(url)
        containers = json.loads(r.read())
        info = {}
        for key, val in containers.iteritems():
            name = key.partition('/')[-1]
            podname = val['proc']
            parts = podname.split('.')
            info[name] = {}
            info[name]['app_name'] = val['app']
            info[name]['node_name'] = val['nodename']
            info[name]['instance_no'] = val['instanceNo']
            info[name]['proc_name'] = parts[-1]
            info[name]['proc_type'] = parts[-2]
        return info

    def get_depends(self):
        # portal:
        # DOMAIN.app.[SERVICE|RESOURCE].portal.PORTALNAME.APPNAME.NODENAME.(instance.NO.)
        url = "%s/v2/depends" % (self.url)
        r = urllib.urlopen(url)
        depends = json.loads(r.read())
        info = {}
        for key, val in depends.iteritems():
            for host, hval in val.iteritems():
                for app, aval in hval.iteritems():
                    service_name, _, _ = key.rsplit('.', 2)
                    service_name = service_name.replace(
                        '.', '_')  # for resource
                    name = "%s-%s-%s" % (key, host, app)
                    info[name] = {}
                    info[name]['app_name'] = app
                    info[name]['node_name'] = host
                    info[name]['portal_name'] = json.loads(
                        aval['Annotation'])['service_name']
                    info[name]['service_name'] = service_name
                    info[name]['proc_name'] = None
                    info[name]['proc_type'] = None
        return info

    @classmethod
    def get_info(cls, containers, depends, container_id, container_name):
        info = {}
        if container_id in containers:
            info["endpoint"] = containers[container_id]["app_name"]
            info["metric"] = "%s-%s-%s" % (
                containers[container_id]["proc_type"],
                containers[container_id]["proc_name"],
                containers[container_id]["instance_no"],
            )
            return info
        name = container_name.rpartition('.')[0]
        if name in depends:
            info["endpoint"] = depends[name]["service_name"],
            info["metric"] = "portal-%s-%s-%s" % (
                depends[name]["portal_name"],
                depends[name]["app_name"],
                depends[name]["node_name"],
            )
            return info
        return info

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lainlet-endpoint", help="lainlet endpoint",
                        default="http://lainlet.lain:9001", type=str)
    parser.add_argument("--domain", help="lain domain",
                        default="lain.local", type=str)
    args = parser.parse_args()
    lainlet = Lainlet(args.lainlet_endpoint, socket.gethostname())

    containers = lainlet.get_containers()
    depends = lainlet.get_depends()

    for container in Docker.get_all_running_containers():
        # eg: mysql-service.portal.portal-mysql-master-xyz-101-hedwig.v0-i0-d0
        # eg: webrouter.worker.worker.v8-i1-d0
        # eg: resource.hello-server.perf.worker.hello.v0-i2-d0
        container_name = container["Names"][0].strip('/')
        container_id = container["Id"]
        stats = Docker.get_stats(container_id)
        lain_info = lainlet.get_info(
            containers, depends, container_id, container_name)

        collector = AppCollector(stats, lain_info)
        collector.run()
