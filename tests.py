# Copyright 2022 Darktrace Holdings Ltd. All rights reserved.
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


from storage import CalculateClosestBucket

results_map = {
    'EUROPE-WEST2': 'EUROPE-WEST2',
    'EUROPE-SOUTH1': 'EUROPE-SOUTHWEST1',
    'EUROPE-EAST2': 'EUROPE-CENTRAL2',
    'SOMEWHERE-WEST3': 'US-CENTRAL1'
}
for location in results_map.keys():
    print('Testing {} == {}'.format(location, results_map[location]))
    result = CalculateClosestBucket(location)
    print('Got: ', result)
    assert result == results_map[location]
print('Pass!')
