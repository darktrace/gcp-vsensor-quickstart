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

"""Deploys a GCP Storage bucket for storing PCAP data, granting permission to
the vSensor service account."""

import re

# Select a close storage bucket location for the selected compute region


def CalculateClosestBucket(compute_region):
    # https://cloud.google.com/storage/docs/locations
    bucket_locations = [
        'NORTHAMERICA-NORTHEAST1',
        'NORTHAMERICA-NORTHEAST2',
        'US-CENTRAL1',
        'US-EAST1',
        'US-EAST4',
        'US-EAST5',
        'US-SOUTH1',
        'US-WEST1',
        'US-WEST2',
        'US-WEST3',
        'US-WEST4',
        'SOUTHAMERICA-EAST1',
        'SOUTHAMERICA-WEST1',
        'EUROPE-CENTRAL2',
        'EUROPE-NORTH1',
        'EUROPE-SOUTHWEST1',
        'EUROPE-WEST1',
        'EUROPE-WEST2',
        'EUROPE-WEST3',
        'EUROPE-WEST4',
        'EUROPE-WEST6',
        'EUROPE-WEST8',
        'EUROPE-WEST9',
        'ASIA-EAST1',
        'ASIA-EAST2',
        'ASIA-NORTHEAST1',
        'ASIA-NORTHEAST2',
        'ASIA-NORTHEAST3',
        'ASIA-SOUTH1',
        'ASIA-SOUTH2',
        'ASIA-SOUTHEAST1',
        'ASIA-SOUTHEAST2',
        'ME-WEST1',
        'AUSTRALIA-SOUTHEAST1',
        'AUSTRALIA-SOUTHEAST2'
    ]
    compute_region = compute_region.upper()
    if compute_region in bucket_locations:
        return compute_region

    # Remove numbers from compute region, e.g. "EUROPE-WEST" from "EUROPE-WEST2"
    sub_region = re.sub(r'\d+', '', compute_region)

    # Find all regions starting with the same sub region (e.g. returns a list of ["EUROPE-WEST1"...] for "EUROPE-WEST")
    same_sub = list(
        filter(lambda region: region.startswith(sub_region), bucket_locations))

    # If we've got one in the valid list of bucket URLS, pick that
    if len(same_sub) > 0:
        return same_sub[0]

    # They don't support storage in this sub region, go to the next major region (e.g. EUROPE) and pick from options there
    same_major = list(filter(lambda region: region.startswith(
        sub_region.split('-', 1)[0]), bucket_locations))

    # If we've got one in the valid list of bucket URLS, pick that
    if len(same_major) > 0:
        return same_major[0]

    # This region doesn't have any bucket storage location. Pick one with the cheaper standard storage.
    return 'US-CENTRAL1'


def GenerateConfig(context):
    """Generates YAML resource configuration."""

    name = context.env['name']
    project = context.env['project']

    prop = context.properties
    gprop = prop['global']

    region = gprop['region']
    service_account_email = prop['service-account-email']
    deployment_hash = prop['deployment-hash']

    retention_time_days = gprop['pcap-retention-time-days']
    retention_time_secs = retention_time_days * 24 * 60 * 60

    BUCKET_NAME = name + '-bucket'
    IAM_ROLE_NAME = deployment_hash + '_vsensor_storage'

    resources = [
        {
            'name': IAM_ROLE_NAME,
            'type': 'gcp-types/iam-v1:projects.roles',
            'properties': {
                'parent': 'projects/'+project,
                'roleId': IAM_ROLE_NAME,
                'role': {
                    'title': 'vSensor IAM Role',
                    'description': 'Gives the vSensor permission to check the GCP bucket is private before use.',
                    'includedPermissions': [
                        'storage.buckets.get'
                    ],
                    'stage': 'GA'
                }
            }
        },
        {
            'name': BUCKET_NAME,
            'type': 'storage.v1.bucket',
            'properties': {
                'iamConfiguration': {
                    'publicAccessPrevention': 'enforced',
                    'uniformBucketLevelAccess': {
                        'enabled': True
                    }
                },
                'location': CalculateClosestBucket(region),
                'lifecycle': {
                    'rule': [
                        {
                            'action': {'type': 'Delete'},
                            'condition': {
                                'age': retention_time_days
                            }
                        }]
                },
                'retentionPolicy': {
                    'retentionPeriod': retention_time_secs
                },
                'storageClass': 'STANDARD',

            },
            'accessControl': {
                'gcpIamPolicy': {
                    'bindings': [
                        {
                            'role': 'roles/storage.objectAdmin',
                            'members': [
                                'serviceAccount:' +
                                service_account_email
                            ]
                        },
                        {
                            # https://cloud.google.com/storage/docs/access-control/iam#convenience-values
                            # Allow the project owner to be able to delete the deployment/bucket again.
                            # If this is removed, the owner cannot read/modify the bucket.
                            'role': 'roles/storage.legacyBucketOwner',
                            'members': [
                                'projectOwner:' +
                                project
                            ]
                        },
                        {
                            # If this is removed, the owner cannot manage storage holds to delete keys.
                            'role': 'roles/storage.objectAdmin',
                            'members': [
                                'projectOwner:' +
                                project
                            ]
                        },
                        {
                            'role': f'projects/{project}/roles/{IAM_ROLE_NAME}',
                            'members': [
                                'serviceAccount:' +
                                service_account_email
                            ]
                        },
                    ]
                }
            }
        }
    ]

    outputs = [
        {
            'name': 'bucket-name',
            'value': BUCKET_NAME
        }
    ]

    return {'resources': resources, 'outputs': outputs}
