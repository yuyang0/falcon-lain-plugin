#!/usr/bin/python
# -*- coding:utf-8 -*-


import os
import time
import socket
import psutil
import argparse
import json


def convert_to_byte(value, scale):
    SIZE_KB = 1 << 10
    SIZE_MB = 1 << 20
    SIZE_GB = 1 << 30
    SIZE_TB = 1 << 40

    SCALE_MAP = {
        "KB": SIZE_KB,
        "MB": SIZE_MB,
        "GB": SIZE_GB,
        "TB": SIZE_TB,
        "B":  1,
    }

    if scale in SCALE_MAP:
        return float(value) * SCALE_MAP[scale]
    else:
        return 0


class ClusterPlugin(object):
    _result = []
    _step = 60
    _endpoint = "lain"
    _host = socket.gethostname()

    def __init__(self, swarm_manager_port, docker_port, ceph_fuse):
        self._swarm_manager_port = swarm_manager_port
        self._docker_port = docker_port
        self._ceph_fuse = ceph_fuse

    def run(self):
        self._result = []
        self.prepare_data()
        print(json.dumps(self._result))

    def prepare_data(self):
        self._result = []
        self._get_cali_veth_stat()
        self._get_ceph_stat()
        return self._result

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

    def _get_cali_veth_stat(self):
        '''
        Check the status of all network interfaces.
        Value is 1 if any one of them is DOWN
        '''
        cali_veth_up = 0
        cali_veth_down = 0
        cali_veth_total = 0
        tmp_veth_up = 0
        tmp_veth_down = 0
        tmp_veth_total = 0
        for name, stat in psutil.net_if_stats().iteritems():
            if name.startswith('cali'):
                cali_veth_total += 1
                if stat.isup:
                    cali_veth_up += 1
                else:
                    cali_veth_down += 1
            elif name.startswith('tmp'):
                tmp_veth_total += 1
                if stat.isup:
                    tmp_veth_up += 1
                else:
                    tmp_veth_down += 1
        self._append_result(
            "lain.node.calico.veth.cali.up",
            self._endpoint, cali_veth_up, self._step)
        self._append_result(
            "lain.node.calico.veth.cali.down",
            self._endpoint, cali_veth_down, self._step)
        self._append_result(
            "lain.node.calico.veth.cali.total",
            self._endpoint, cali_veth_total, self._step)
        self._append_result(
            "lain.node.calico.veth.tmp.up",
            self._endpoint, tmp_veth_up, self._step)
        self._append_result(
            "lain.node.calico.veth.tmp.down",
            self._endpoint, tmp_veth_down, self._step)
        self._append_result(
            "lain.node.calico.veth.tmp.total",
            self._endpoint, tmp_veth_total, self._step)

    def _get_ceph_stat(self):
        '''
        Get the mfs status
        '''
        is_mounted = 1 if os.path.ismount(self._ceph_fuse) else 0
        self._append_result(
            "lain.cluster.cephfuse.mounted", self._endpoint,
            is_mounted, self._step)

    def _get_size_byte(self, size_str):
        parts = size_str.split(" ")
        if len(parts) == 2:
            return convert_to_byte(parts[0], parts[1])
        else:
            return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose', action="store_true")
    parser.add_argument("--swarm-manager-port", help="Swarm manager port",
                        default=2376, type=int)
    parser.add_argument("--docker-port", help="Dockerd port",
                        default=2375, type=int)
    parser.add_argument("--ceph-fuse", help="Ceph fuse mountpoint",
                        default="/cephfs", type=str)

    args = parser.parse_args()
    cluster_plugin = ClusterPlugin(args.swarm_manager_port, args.docker_port, args.ceph_fuse)
    if args.verbose:
        cluster_plugin.verbose()
    else:
        cluster_plugin.run()
