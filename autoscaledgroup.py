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

"""Creates an auto-scaling Managed Instance Group of vSensors to ingest Packet
Mirroring and osSensor traffic."""

from common import (
    prefixURLCompute,
    getRef,
    GenerateOSSensorLBIP,
    GCP_CLOUD_OPS_TEMPLATE,
)


def GenerateConfig(context):
    name = context.env["name"]
    project = context.env["project"]

    # Template properties
    prop = context.properties
    gprop = prop["global"]

    vpc_ref = prop["vpc-ref"]
    subnet_ref = prop["subnet-ref"]
    health_check_name = prop["healthcheck-name"]
    service_account_email = prop["service-account-email"]
    # GCP detects this as a dependency, so remove dependency if PCAP storage should be disabled
    pcap_bucket_name = (
        prop["pcap-bucket-name"] if (gprop["pcap-retention-time-days"] != 0) else ""
    )

    zone_1 = prefixURLCompute(context, "zones/" + gprop["zone1"])
    zone_2 = prefixURLCompute(context, "zones/" + gprop["zone2"])

    region = gprop["region"]
    min_size = gprop["mig-min-size"]
    max_size = gprop["mig-max-size"]
    instance_type = gprop["mig-instance-type"]
    vsensor_update_key = gprop["vsensor-update-key"]
    appliance_push_token = gprop["appliance-push-token"]
    appliance_hostname = gprop["appliance-hostname"]
    appliance_port = gprop["appliance-port"]
    ossensor_hmac = gprop["ossensor-hmac"] if "ossensor-hmac" in gprop else ""
    mig_subnet_cidr = gprop["mig-subnet-cidr"]
    username_sshkey = gprop["mig-ssh-user-key"] if "mig-ssh-user-key" in gprop else None
    ipv6 = gprop["ipv6-enable"]
    ossensor_lb_ip = GenerateOSSensorLBIP(mig_subnet_cidr)

    BASE_NAME = name + "-vsensor"
    MIG_NAME = name + "-group"
    INSTANCE_TEMPLATE_NAME = name + "-template"

    # https://cloud.google.com/compute/docs/reference/rest/v1/instanceTemplates/insert

    instance_template = {
        "name": INSTANCE_TEMPLATE_NAME,
        "type": "compute.v1.instanceTemplate",
        "properties": {
            "properties": {
                "machineType": instance_type,
                "tags": {"items": ["darktrace-vsensor-mirroring", "darktrace-ssh-iap"]},
                "disks": [
                    {
                        "deviceName": "boot",
                        "type": "PERSISTENT",
                        "boot": True,
                        "autoDelete": True,
                        "initializeParams": {
                            "sourceImage": prefixURLCompute(
                                context,
                                "projects/ubuntu-os-cloud/global/images/family/ubuntu-2004-lts",
                                False,
                            ),
                            "diskSizeGb": 20,
                            "diskType": "pd-balanced",
                            "labels": {"darktrace-vsensor": "true"},
                        },
                    }
                ],
                "networkInterfaces": [
                    {
                        "network": vpc_ref,
                        "subnetwork": subnet_ref,
                        "stackType": "IPV4_IPV6" if ipv6 else "IPV4_ONLY",
                    }
                ],
                "canIpForward": True,  # Allow RESPOND/Network packets,
                "serviceAccounts": [
                    {
                        "email": service_account_email,
                        # Sets scope at the service account level, rather than at the instance level.
                        "scopes": ["https://www.googleapis.com/auth/cloud-platform"],
                    }
                ],
                "metadata": {
                    "items": [
                        # autopep8: off
                        {
                            "key": "startup-script",
                            "value": f"""
                          #! /bin/bash -xe
                          function exittrap() {{
                            exitcode="$?"
                            set +e
                            if [ "$exitcode" -gt 0 ]; then
                                echo "Failed to successfully configure vSensor, more details in /var/log/user-data.log"
                                all-services.sh -f nginx stop
                                echo "Instance marked as unhealthy."
                            fi
                            exit "$exitcode"
                          }}

                          exec > >(tee -a /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

                          trap exittrap EXIT
                          
                          echo "Starting userdata, installing Cloud OPS agent for logging"
                          curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
                          bash add-google-cloud-ops-agent-repo.sh --also-install
                          cat >/etc/google-cloud-ops-agent/config.yaml <<EOF
                            {GCP_CLOUD_OPS_TEMPLATE}
EOF
                          service google-cloud-ops-agent restart
                          echo "Completed Google Cloud Ops Configuration"
                          echo "Starting vSensor installation"
                          bash <(wget -O - https://packages.darktrace.com/install) --updateKey {vsensor_update_key}
                          echo "Setting configuration"
                          #set updatekey, upgrade and enable daily updates
                          set_updatekey.sh {vsensor_update_key}
                          set_pushtoken.sh {appliance_push_token} {appliance_hostname}:{appliance_port}
                          set_ossensor_loadbalancer_direct.sh 1 # Allow osSensors to work via load balancer
                          set_ephemeral.sh 1 # Configure vSensor for use in ASG.
                          if [ -n "{ossensor_hmac}" ]; then
                            set_ossensor_hmac.sh {ossensor_hmac}
                            set_gcp_lb_ip.sh "{ossensor_lb_ip}"
                          fi
                          if [ -n "{pcap_bucket_name}" ]; then
                            set_pcap_gcp_bucket.sh "{pcap_bucket_name}" "{service_account_email}"
                          else
                            set_pcap_size.sh 0
                          fi
                          echo "Completed vSensor configuration"
                        """,
                        }
                        # autopep8: on
                    ]
                },
            }
        },
    }

    # Because pcap_bucket_name is optional above, it doesn't detect the dependency implicitly.
    # Add it explicitly here. This gets appended to the implict ones for the VPC, Subnet and Service Account.
    if pcap_bucket_name:
        instance_template["metadata"] = {"dependsOn": [pcap_bucket_name]}

    if username_sshkey:
        instance_template["properties"]["properties"]["metadata"]["items"].append(
            {"key": "ssh-keys", "value": username_sshkey}
        )

    # Use BETA for minReadySec: https://cloud.google.com/compute/docs/reference/rest/beta/instanceGroupManagers
    resources = [
        {
            "name": MIG_NAME,
            "type": "compute.beta.regionInstanceGroupManager",
            "properties": {
                "description": "Managed Instance Group for Darktrace vSensor.",
                "project": project,
                "distributionPolicy": {"zones": [{"zone": zone_1}, {"zone": zone_2}]},
                "region": region,
                # Initial spin up only one vSensor, it will setup the shared storage HMAC key before any others scale up for load.
                "targetSize": 1,
                "baseInstanceName": BASE_NAME,
                "instanceTemplate": getRef(INSTANCE_TEMPLATE_NAME),
                "updatePolicy": {
                    "type": "PROACTIVE",
                    "minimalAction": "REPLACE",
                    "minReadySec": 180,
                },
                "autoHealingPolicies": [
                    {"healthCheck": getRef(health_check_name), "initialDelaySec": 300}
                ],
            },
            "metadata": {"dependsOn": [health_check_name]},
        },
        {
            "name": name + "-autoscale",
            "type": "compute.v1.regionAutoscaler",
            "properties": {
                "region": region,
                "description": "Managed Instance Group for Darktrace vSensor.",
                "target": getRef(MIG_NAME),
                "autoscalingPolicy": {
                    "minNumReplicas": min_size,
                    "maxNumReplicas": max_size,
                    "scaleDownControl": {
                        "maxScaledDownReplicas": {"fixed": 1},
                        "timeWindowSec": 600,
                    },
                    "coolDownPeriodSec": 300,
                    "cpuUtilization": {
                        "utilizationTarget": 0.75,
                        "predictiveMethod": "OPTIMIZE_AVAILABILITY",
                    },
                },
            },
        },
    ]
    resources.append(instance_template)

    outputs = [
        {"name": "mig-name", "value": MIG_NAME},
        {"name": "mig-ref", "value": getRef(MIG_NAME)},
        {"name": "mig-ig-ref", "value": getRef(MIG_NAME, "instanceGroup")},
    ]

    return {"resources": resources, "outputs": outputs}
