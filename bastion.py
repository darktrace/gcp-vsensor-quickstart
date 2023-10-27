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

"""Creates a Bastion host for accessing the vSensors in the private subnet."""

from common import getRef, prefixURLCompute


def GenerateConfig(context):
    """Generate one autoscaled_group resource Dict with a passed zone."""
    name = context.env['name']
    project = context.env['project']
    prop = context.properties
    gprop = prop['global']
    vpc_ref = prop['vpc-ref']
    deployment_hash = prop['deployment-hash']
    service_account_id = '-'.join([name[:17], deployment_hash, 'bsa'])

    region = gprop['region']
    cidr_range = gprop['bastion-subnet-cidr']
    external_cidr_ranges = [gprop['bastion-external-cidr']]
    zone_1 = prefixURLCompute(context, 'zones/'+gprop['zone1'])
    zone_2 = prefixURLCompute(context, 'zones/'+gprop['zone2'])
    username_sshkey = gprop['bastion-ssh-user-key'] if 'bastion-ssh-user-key' in gprop else None

    INSTANCE_TEMPLATE_NAME = name+'-template'
    SUBNET_NAME = name + '-subnet'

    # https://cloud.google.com/compute/docs/reference/rest/v1/instanceTemplates/insert
    instance_template = {
        'name': INSTANCE_TEMPLATE_NAME,
        'type': 'compute.v1.instanceTemplate',
        'properties': {
            'properties': {
                'tags': {
                    'items': ['darktrace-vsensor-bastion']
                },
                'machineType': 'e2-micro',
                'disks': [{
                    'deviceName': 'boot',
                    'type': 'PERSISTENT',
                    'boot': True,
                    'autoDelete': True,
                    'initializeParams': {
                        'sourceImage': prefixURLCompute(context, 'projects/ubuntu-os-cloud/global/images/family/ubuntu-2004-lts', False),
                        'diskSizeGb': 10,
                        'diskType': 'pd-standard'
                    },

                }],
                'networkInterfaces': [{
                    'network': vpc_ref,
                    'subnetwork': getRef(SUBNET_NAME),
                    'accessConfigs': [
                        {
                            'name': 'External NAT',
                            'type': 'ONE_TO_ONE_NAT',
                            'networkTier': 'PREMIUM'
                        }
                    ],
                }],
                'serviceAccounts': [{
                    'email': getRef(service_account_id, 'email'),
                    # Sets scope at the service account level, rather than at the instance level.
                    'scopes': ['https://www.googleapis.com/auth/cloud-platform']
                }],
                'metadata': {
                    'items': [
                        {
                            'key': 'startup-script',
                            'value': """
                                #! /bin/bash -xe
                                exec > >(tee -a /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1
                                echo "Installing Monitoring Agent"
                                curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
                                bash add-google-cloud-ops-agent-repo.sh --also-install
                            """
                        }
                    ]
                }
            }
        }
    }

    if username_sshkey:
        instance_template['properties']['properties']['metadata']['items'].append(
            {
                'key': 'ssh-keys',
                'value': username_sshkey
            }
        )

    resources = [
        {
            'name': SUBNET_NAME,
            'type': 'compute.v1.subnetwork',
            'properties': {
                'description': 'Public subnet containing bastion for Darktrace vSensors',
                'network': vpc_ref,
                'ipCidrRange': cidr_range,
                'region': region,
                'privateIpGoogleAccess': True,
            }
        },
        {
            'name': name + '-firewall-internal',
            'type': 'compute.v1.firewall',
            'properties': {
                'description': 'vSensor Quickstart bastion public firewall policy. This allows access to the bastion (and therefore vSensors) from an external CIDR range.',
                'name': 'External SSH Access',
                'priority': 1000,
                'network': vpc_ref,
                'sourceRanges': external_cidr_ranges,
                'direction': 'INGRESS',
                'allowed': [
                    {
                        'IPProtocol': 'TCP',
                        'ports': [
                            '22'
                        ]
                    },
                    {
                        'IPProtocol': 'icmp'
                    }
                ]
            }
        },
        # Service account to auth Bastion
        {
            'name': service_account_id,
            'type': 'iam.v1.serviceAccount',
            'properties': {
                'accountId': service_account_id,
                'displayName': 'Darktrace vSensor Quickstart Bastion',
                'description': 'Allows Bastion to send logs / metrics from Monitoring Ops Agent'
            }
        },
        # Give Bastion service account permissions to send Ops Agent logging/metrics.
        {
            'name': service_account_id + '-iam',
            'type': 'iam_member.py',
            'properties': {
                'roles': [{
                    'role': 'roles/monitoring.metricWriter',
                    'members': [
                        'serviceAccount:$(ref.{}.email)'.format(
                            service_account_id)
                    ]
                },
                    {
                    'role': 'roles/logging.logWriter',
                    'members': [
                        'serviceAccount:$(ref.{}.email)'.format(
                            service_account_id)
                    ],
                }]
            }
        },
        {
            'name': name + '-mig',
            'type': 'compute.v1.regionInstanceGroupManager',
            'properties': {
                'description': 'Managed Instance Group for Bastion in vSensor Quickstart.',
                'project': project,
                'distributionPolicy': {
                    'zones': [
                        {
                            'zone': zone_1,
                        },
                        {
                            'zone': zone_2,
                        }
                    ]
                },
                'region': region,
                'targetSize': 1,
                'baseInstanceName': name + '-vm',
                'instanceTemplate': getRef(INSTANCE_TEMPLATE_NAME),
                'updatePolicy': {
                    'type': 'PROACTIVE'
                }
            }
        }
    ]
    resources.append(instance_template)

    outputs = [
        {
            'name': 'subnet-ref',
            'value': getRef(SUBNET_NAME),
        },
        {
            'name': 'subnet-name',
            'value': SUBNET_NAME
        }
    ]

    return {'resources': resources, 'outputs': outputs}
