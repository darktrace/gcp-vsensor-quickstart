# Copyright 2022 Darktrace Holdings Ltd. All rights reserved.
# Based on modified example code: Copyright 2022 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shared functions and long static code blocks used by the GCP Quick Start."""

import ipaddress

# URL constants
COMPUTE_URL_BASE = "https://www.googleapis.com/compute/v1/"

# autopep8: off
GCP_CLOUD_OPS_TEMPLATE = """
logging:
    receivers:
        vsensor-syslog:
            type: files
            include_paths:
                - /var/log/messages
                - /var/log/syslog
        vsensor-updates:
            type: files
            include_paths:
                - /var/log/darktrace-apt-dist-upgrade.log
                - /var/log/dpkg.log
                - /var/log/apt/term.log
                - /var/log/apt/history.log
        vsensor-services:
            type: files
            include_paths:
                - /var/log/sabreserver/*
                - /var/log/darktrace-sabre-mole/manager.log
                - /var/log/nginx/access.log
                - /var/log/bro/*
                - /var/opt/bro/spool/manager/*
                - /var/log/darktrace-*
                - /var/log/inithooks.log
                - /var/log/heka/*
                - /var/log/redis/*
        vsensor-userdata:
            type: files
            include_paths:
                - /var/log/user-data.log
    service:
        pipelines:
            default_pipeline:
                receivers: [vsensor-syslog,vsensor-updates,vsensor-services,vsensor-userdata]
metrics:
    receivers:
        hostmetrics:
            type: hostmetrics
            collection_interval: 60s
    processors:
        metrics_filter:
            type: exclude_metrics
            metrics_pattern: []
    service:
        pipelines:
            default_pipeline:
                receivers: [hostmetrics]
                processors: [metrics_filter]
"""
# autopep8: on


def getRef(resource, output="selfLink"):
    return "$(ref.{}.{})".format(resource, output)


def prefixURLCompute(context, path, prefix_project=True):
    project_name = context.env["project"]
    if prefix_project:
        return "".join([COMPUTE_URL_BASE, "projects/", project_name, "/", path])
    return COMPUTE_URL_BASE + path


def GlobalComputeLink(project, collection, name):
    return "".join(
        [COMPUTE_URL_BASE, "projects/", project, "/global/", collection, "/", name]
    )


def RegionComputeLink(project, collection, name, region):
    return "".join(
        [
            COMPUTE_URL_BASE,
            "projects/",
            project,
            "/regions/",
            region,
            "/",
            collection,
            "/",
            name,
        ]
    )


def GenerateOSSensorLBIP(cidr_range):
    # We will be giving it the range of the vSensor subnet, the MIG starts from lowest IP first,
    # so should be good to pick the last IP in the cidr.
    ips = [str(ip) for ip in ipaddress.IPv4Network(cidr_range)]
    # Take the third largest IP in that range, give it to the LB. #Broadcast uses -1, something else is in -2.
    return ips[-3]
