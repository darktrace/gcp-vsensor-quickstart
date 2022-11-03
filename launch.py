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

"""Main launch template for Google Deployment Manager to deploy Darktrace
vSensors into a GCP project."""

# https://cloud.google.com/deployment-manager/docs/configuration/supported-resource-types

import hashlib
from common import getRef

def validation(context):
    name = context.env['deployment']
    prop = context.properties

    errors = []
    if len(name) > 40:
        errors.append(
            'Deployment name is too long. Choose a name 40 characters or less.')
    if prop['mig-min-size'] > prop['mig-max-size']:
        errors.append(
            'vSensor Managed Instance Group size minimum is larger than the maximum.')
    if prop['bastion-enable'] and ('bastion-subnet-cidr' not in prop or 'bastion-external-cidr' not in prop):
        errors.append(
            'Bastion subnet and external IP CIDRs are required if bastion-enable is True.')
    if errors:
        raise Exception(
            'The deployment configuration has not passed validation:\n    - '+'\n    - '.join(errors))


def GenerateConfig(context):
    """Generate YAML resource configuration."""

    validation(context)

    name = context.env['deployment']

    # Some resource names (ie Service account) must be short.
    # Generate a unique-enough ID such that multiple deployments don't interfere.
    deployment_hash = hashlib.md5(name.encode('utf-8'))
    deployment_hash = deployment_hash.hexdigest()[:8]

    service_account_id = '-'.join([name[:18], deployment_hash, 'sa'])

    # Template properties
    prop = context.properties
    bastion_enable = prop['bastion-enable']
    mig_subnet_cidr = prop['mig-subnet-cidr']
    ossensor_lb_enable = 'ossensor-hmac' in prop and prop['ossensor-hmac'] != ''

    HEALTHCHECK_NAME = name + '-healthcheck'
    NETWORK_TEMPLATE_NAME = name + '-net'
    MIG_TEMPLATE_NAME = name + '-vsensor-mig'
    BASTION_TEMPLATE_NAME = name + '-bastion'
    STORAGE_TEMPLATE_NAME = name + '-storage'
    INGEST_TEMPLATE_NAME = name + '-ingestion'

    resources = [
        # Setup the VPC and vSensor Subnet
        {
            'name': NETWORK_TEMPLATE_NAME,
            'type': 'network.py',
            'properties': {
                'global': prop
            }
        },
        # Service account to auth vSensor
        {
            'name': service_account_id,
            'type': 'iam.v1.serviceAccount',
            'properties': {
                'accountId': service_account_id,
                'displayName': 'Darktrace vSensor Quickstart',
                'description': 'Allows Darktrace vSensors to read/write PCAPs to Storage Bucket'
            }
        },
        # Give vSensor service account permissions to manage storage keys and Ops Agent logging/metrics.
        {
            'name': service_account_id + '-iam',
            'type': 'iam_member.py',
            'properties': {
                'roles': [{
                    'role': 'roles/storage.hmacKeyAdmin',
                    'members': [
                        'serviceAccount:$(ref.{}.email)'.format(
                            service_account_id)
                    ]
                },
                    {
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
        # Create a Storage Bucket to permanently store PCAPS across vSensor scaling
        {
            'name': STORAGE_TEMPLATE_NAME,
            'type': 'storage.py',
            'properties': {
                'vpc-ref': getRef(NETWORK_TEMPLATE_NAME, 'vpc-ref'),
                'global': prop,
                'service-account-email': getRef(service_account_id, 'email'),
                'deployment-hash': deployment_hash
            },
            'metadata': {
                'dependsOn': [
                    MIG_TEMPLATE_NAME
                ]
            }
        },
        # Generate an Autoscaling Managed Instance Group containing vSensors.
        {
            'name': MIG_TEMPLATE_NAME,
            'type': 'autoscaledgroup.py',
            'properties': {
                'vpc-ref': getRef(NETWORK_TEMPLATE_NAME, 'vpc-ref'),
                'subnet-ref': getRef(NETWORK_TEMPLATE_NAME, 'subnet-ref'),
                'healthcheck-name': HEALTHCHECK_NAME,
                'global': prop,
                'deployment-hash': deployment_hash,
                'service-account-email': getRef(service_account_id, 'email'),
                'pcap-bucket-name': getRef(STORAGE_TEMPLATE_NAME, 'bucket-name')
            }
        },
        # Health check used by load balancer and Instance Group.
        {
            'name': HEALTHCHECK_NAME,
            'type': 'compute.v1.healthCheck',
            'properties': {
                'httpsHealthCheck': {
                    'port': 443,
                    'requestPath': '/',
                },
                'type': 'HTTPS'
            }
        },
    ]
    # Optionally configure a Bastion host to allow external access to the vSensors.
    bastion_subnet_ref = None
    if bastion_enable:
        resources.append(
            {
                'name': BASTION_TEMPLATE_NAME,
                'type': 'bastion.py',
                'properties': {
                    'vpc-ref': getRef(NETWORK_TEMPLATE_NAME, 'vpc-ref'),
                    'global': prop,
                    'deployment-hash': deployment_hash
                }
            })
        bastion_subnet_ref = getRef(BASTION_TEMPLATE_NAME, 'subnet-ref')

    resources.append(
        # Configure a load balancer for osSensor and packet mirroring
        {
            'name': INGEST_TEMPLATE_NAME,
            'type': 'loadbalancer.py',
            'properties': {
                'vpc-ref': getRef(NETWORK_TEMPLATE_NAME, 'vpc-ref'),
                'mig-ig-ref': getRef(MIG_TEMPLATE_NAME, 'mig-ig-ref'),
                'mig-subnet-ref': getRef(NETWORK_TEMPLATE_NAME, 'subnet-ref'),
                'bastion-subnet-ref': bastion_subnet_ref,
                'mirrored-subnet-names': [],  # TODO
                'healthcheck-name': HEALTHCHECK_NAME,
                'global': prop
            }
        }
    )

    outputs = [
        {
            'name': 'vpc-name',
            'value': getRef(NETWORK_TEMPLATE_NAME, 'vpc-name')
        },
        {
            'name': 'nat-external-ip',
            'value': getRef(NETWORK_TEMPLATE_NAME, 'nat-ip')
        },
        {
            'name': 'pcap-bucket-name',
            'value': getRef(STORAGE_TEMPLATE_NAME, 'bucket-name')
        },
        {
            'name': 'vsensor-subnet-name',
            'value': getRef(NETWORK_TEMPLATE_NAME, 'subnet-name')
        }
    ]
    if bastion_enable:
        outputs.extend([
            {
                'name': 'bastion-subnet-name',
                'value': getRef(BASTION_TEMPLATE_NAME, 'subnet-name')
            }
        ])
    if ossensor_lb_enable:
        outputs.extend([
            {
                'name': 'ossensor-vsensor-ip',
                'value': getRef(INGEST_TEMPLATE_NAME, 'ossensor-loadbalancer-ip')
            },
            {
                'name': 'ossensor-vsensor-cidr',
                'value': mig_subnet_cidr
            }
        ])

    return {'resources': resources, 'outputs': outputs}
