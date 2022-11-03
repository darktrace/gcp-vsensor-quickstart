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

"""Creates a VPC and subnet to deploy the Darktrace vSensor instances and
associated resources into."""

from common import getRef, GlobalComputeLink


def GenerateConfig(context):
    """Generates YAML resource configuration."""

    name = context.env['name']
    project = context.env['project']
    prop = context.properties
    # Properties from the launch
    gprop = prop['global']

    cidr_range = gprop['mig-subnet-cidr']
    region = gprop['region']
    existing_vpc_name = gprop['existing-vpc-name'] if 'existing-vpc-name' in gprop else None

    VPC_NAME = existing_vpc_name if existing_vpc_name else (name + '-vpc')
    SUBNET_NAME = name + '-vsensor-subnet'
    NAT_IP_NAME = name + '-nat-external-ip'

    resources = []
    # If customer provides an existing VPC to launch into, don't directly add it to the deployment, deployment manager will try to delete it.
    if existing_vpc_name:
        network_ref = GlobalComputeLink(project, 'networks', existing_vpc_name)
    else:
        network_ref = getRef(VPC_NAME)
        # Create a new VPC.
        resources.append(
            {
                'name': VPC_NAME,
                'type': 'compute.v1.network',
                'properties': {
                    'routingConfig': {
                        'routingMode': 'REGIONAL'
                    },
                    'autoCreateSubnetworks': False
                }
            }
        )

    resources.extend([
        {
            'name': SUBNET_NAME,
            'type': 'compute.v1.subnetwork',
            'properties': {
                'description': 'Subnet containing Darktrace vSensors. DO NOT apply traffic mirroring to this subnet.',
                'network': network_ref,
                'ipCidrRange': cidr_range,
                'region': region,
                'privateIpGoogleAccess': True
            }
        },
        # https://cloud.google.com/iap/docs/using-tcp-forwarding
        {
            'name': name + '-firewall-ssh-iap',
            'type': 'compute.v1.firewall',
            'properties': {
                'description': 'vSensor Quickstart Firewall Policy for SSH-in-browser and IAP',
                'name': 'Allow All Mirror Traffic',
                'priority': 1000,
                'network': network_ref,
                'sourceRanges': [
                    '35.235.240.0/20'
                ],
                # Apply firewall rule to only vSensors and bastion in MIG.
                'targetTags': [
                    'darktrace-vsensor-mirroring',
                    'darktrace-vsensor-bastion'
                ],
                'logConfig': {
                    'enable': False
                },
                'direction': 'INGRESS',
                'allowed': [
                    {
                        'IPProtocol': 'TCP',
                        'ports': [
                            '22'
                        ]
                    }
                ]
            }
        },

        {
            'name': name + '-firewall-traffic-mirror',
            'type': 'compute.v1.firewall',
            'properties': {
                'name': 'vSensor Quickstart Traffic Mirroring Firewall Policy',
                'description': 'Allow all packet mirror traffic to be ingested into the vSensors.',
                'priority': 1, # GCP recommended this such that it always applies over other firewall rules.
                'network': network_ref,
                'sourceRanges': [
                    '0.0.0.0/0'
                ],
                # Apply firewall rule to only vSensors in private MIG.
                'targetTags': [
                    'darktrace-vsensor-mirroring'
                ],
                'logConfig': {
                    'enable': False
                },
                'direction': 'INGRESS',
                'allowed': [
                    {
                        'IPProtocol': 'all'
                    }
                ]
            }
        },
        {
            'name': NAT_IP_NAME,
            'type': 'compute.v1.address',
            'properties': {
                'description': 'IP address used for NAT router to allow vSensors access to Appliance / software updates.',
                'addressType': 'EXTERNAL',
                'networkTier': 'PREMIUM',
                'region': region
            }
        },
        {
            'name': SUBNET_NAME+'-router',
            'type': 'compute.v1.router',
            'properties': {
                'description': 'NAT Router for Darktrace vSensors to access internet.',
                'network': network_ref,
                'ipCidrRange': cidr_range,
                'region': region,
                'privateIpGoogleAccess': True,
                'nats': [
                    {
                        'name': SUBNET_NAME+'-nat',
                        'sourceSubnetworkIpRangesToNat': 'ALL_SUBNETWORKS_ALL_IP_RANGES',
                        'natIpAllocateOption': 'MANUAL_ONLY',
                        'natIps': [
                            getRef(NAT_IP_NAME)
                        ]
                    }
                ]
            }
        }
    ])

    outputs = [
        {
            'name': 'vpc-name',
            'value': VPC_NAME
        },
        {
            'name': 'vpc-ref',
            'value': network_ref
        },
        {
            'name': 'subnet-name',
            'value': SUBNET_NAME
        },
        {
            'name': 'subnet-ref',
            'value': getRef(SUBNET_NAME)
        },
        {
            'name': 'nat-ip',
            'value': getRef(NAT_IP_NAME, 'address')
        }
    ]

    return {'resources': resources, 'outputs': outputs}
