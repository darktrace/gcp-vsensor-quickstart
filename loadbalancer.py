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

"""Creates a TCP load balancer backend with forwarding rules for optional
Bastion, packet mirroring and osSensors."""

from common import getRef, GenerateOSSensorLBIP


def GenerateMirrorConfig(project, region, vpc_ref, backend, subnet_name, subnet_ref=None):
    rule_name = 'mirror-' + subnet_name
    return [
        {
            'name': rule_name,
            'type': 'compute.v1.forwardingRule',
                    'properties': {
                        'description': 'Front end forwarding config for vSensor Traffic Mirroring',
                        'IPProtocol': 'TCP',
                        'allPorts': True,
                        'loadBalancingScheme': 'INTERNAL',
                        'subnetwork': subnet_ref if subnet_ref else getRef(subnet_name),
                        'region': region,
                        'backendService': getRef(backend),
                        'ipVersion': 'IPV4',
                        'allowGlobalAccess': False,
                        'isMirroringCollector': True
                    }
        },

        {
            'name': rule_name + '-policy',
            'type': 'gcp-types/compute-v1:packetMirrorings',
                    'properties': {
                        'description': 'Packet mirroring policy for subnetwork: '+subnet_name,
                        'network': {
                            'url': vpc_ref
                        },
                        'name': rule_name + '-policy',
                        'region': region,
                        'projectId': project,
                        'collectorIlb': {
                            'url': getRef(rule_name)
                        },
                        'mirroredResources': {
                            'subnetworks': [{
                                'url': subnet_ref if subnet_ref else getRef(subnet_name)
                            }]
                        }
                    }

        }
    ]


def GenerateConfig(context):
    """Generates YAML resource configuration."""

    name = context.env['name']
    project = context.env['project']
    deployment = context.env['deployment']
    prop = context.properties
    gprop = prop['global']

    # Using Refs doesn't work inside arrays. They don't get resolved.
    # Pass the known bastion subnet in separately.
    bastion_subnet_ref = prop['bastion-subnet-ref']
    # new resource names cannot contain refs to objects, so we must generate this string manually.
    bastion_subnet_name = deployment + '-bastion-subnet'
    mirrored_subnet_names = prop['mirrored-subnet-names']
    vpc_ref = prop['vpc-ref']
    health_check_name = prop['healthcheck-name']
    mig_ig_ref = prop['mig-ig-ref']
    mig_subnet_ref = prop['mig-subnet-ref']

    region = gprop['region']
    mig_subnet_cidr = gprop['mig-subnet-cidr']

    enable_ossensor_lb = 'ossensor-hmac' in gprop and gprop['ossensor-hmac'] != ''

    BACKEND_NAME = name + '-lb-backend'
    FRONTEND_OSSENSOR_NAME = name + '-lb-ossensor'

    resources = [
        {
            'name': BACKEND_NAME,
            'type': 'compute.v1.regionBackendService',
            'properties': {
                'description': 'TCP Load Balancer for accepting Traffic Mirroring',
                'backends': [
                    {
                        'description': 'TCP Backend',
                        'group': mig_ig_ref,
                    }
                ],
                'healthChecks': [
                    getRef(health_check_name)
                ],
                'region': region,
                'loadBalancingScheme': 'INTERNAL',
                'network': vpc_ref,
                'connectionDraining': {
                    'drainingTimeoutSec': 300,
                }

            }
        }
    ]
    if enable_ossensor_lb:
        resources.append({
            'name': FRONTEND_OSSENSOR_NAME,
            'type': 'compute.v1.forwardingRule',
            'properties': {
                    'description': 'Front end forwarding config for vSensor to allow osSensor registrations.',
                    'IPProtocol': 'TCP',
                    'IPAddress': GenerateOSSensorLBIP(mig_subnet_cidr),
                    'ports': ['443'],
                    'loadBalancingScheme': 'INTERNAL',
                    'subnetwork': mig_subnet_ref,
                    'region': region,
                    'backendService': getRef(BACKEND_NAME),
                    'ipVersion': 'IPV4',
                    'allowGlobalAccess': False,
                    'isMirroringCollector': False
            }
        }
        )
    # If customer has enabled bastion, add packet mirroring for that too.
    if bastion_subnet_ref:
        resources.extend(GenerateMirrorConfig(
            project, region, vpc_ref, BACKEND_NAME, bastion_subnet_name, bastion_subnet_ref))

    # Add packet mirroring config for any further subnets to mirror.
    for subnet_name in mirrored_subnet_names:
        resources.extend(
            resources.extend(GenerateMirrorConfig(
                project, region, vpc_ref, BACKEND_NAME, subnet_name))
        )

    outputs = []
    if enable_ossensor_lb:
        outputs = [
            {
                'name': 'ossensor-loadbalancer-ip',
                'value': getRef(FRONTEND_OSSENSOR_NAME, 'IPAddress')
            }
        ]
    return {'resources': resources, 'outputs': outputs}
