# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import datetime
from kubernetes import client as k8s_client
from kubernetes import config
import time
import logging


class K8sHelper(object):
  """ Kubernetes Helper """

  def __init__(self):
    if not self._configure_k8s():
      raise Exception('K8sHelper __init__ failure')

  def _configure_k8s(self):
    config.load_incluster_config()
    self._api_client = k8s_client.ApiClient()
    self._corev1 = k8s_client.CoreV1Api(self._api_client)
    return True

  def _create_k8s_job(self, yaml_spec):
    """ _create_k8s_job creates a kubernetes job based on the yaml spec """
    pod = k8s_client.V1Pod(metadata=k8s_client.V1ObjectMeta(generate_name=yaml_spec['metadata']['generateName']))
    container = k8s_client.V1Container(name = yaml_spec['spec']['containers'][0]['name'],
                                       image = yaml_spec['spec']['containers'][0]['image'],
                                       args = yaml_spec['spec']['containers'][0]['args'],
                                       volume_mounts = [k8s_client.V1VolumeMount(
                                           name=yaml_spec['spec']['containers'][0]['volumeMounts'][0]['name'],
                                           mount_path=yaml_spec['spec']['containers'][0]['volumeMounts'][0]['mountPath'],
                                       )],
                                       env = [k8s_client.V1EnvVar(
                                           name=yaml_spec['spec']['containers'][0]['env'][0]['name'],
                                           value=yaml_spec['spec']['containers'][0]['env'][0]['value'],
                                       )])
    pod.spec = k8s_client.V1PodSpec(restart_policy=yaml_spec['spec']['restartPolicy'],
                                    containers = [container],
                                    service_account_name=yaml_spec['spec']['serviceAccountName'],
                                    volumes=[k8s_client.V1Volume(
                                        name=yaml_spec['spec']['volumes'][0]['name'],
                                        secret=k8s_client.V1SecretVolumeSource(
                                           secret_name=yaml_spec['spec']['volumes'][0]['secret']['secretName'],
                                        )
                                    )])
    try:
      api_response = self._corev1.create_namespaced_pod(yaml_spec['metadata']['namespace'], pod)
      return api_response.metadata.name, True
    except k8s_client.rest.ApiException as e:
      logging.exception("Exception when calling CoreV1Api->create_namespaced_pod: {}\n".format(str(e)))
      return '', False

  def _wait_for_k8s_job(self, pod_name, yaml_spec, timeout):
    """ _wait_for_k8s_job waits for the job to complete """
    status = 'running'
    start_time = datetime.now()
    while status in ['pending', 'running']:
      # Pod pending values: https://github.com/kubernetes-client/python/blob/master/kubernetes/docs/V1PodStatus.md
      try:
        api_response = self._corev1.read_namespaced_pod(pod_name, yaml_spec['metadata']['namespace'])
        status = api_response.status.phase.lower()
        time.sleep(5)
        elapsed_time = (datetime.now() - start_time).seconds
        logging.info('{} seconds: waiting for job to complete'.format(elapsed_time))
        if elapsed_time > timeout:
          logging.info('Kubernetes job timeout')
          return False
      except k8s_client.rest.ApiException as e:
        logging.exception('Exception when calling CoreV1Api->read_namespaced_pod: {}\n'.format(str(e)))
        return False
    return status == 'succeeded'

  def _delete_k8s_job(self, pod_name, yaml_spec):
    """ _delete_k8s_job deletes a pod """
    try:
      api_response = self._corev1.delete_namespaced_pod(pod_name, yaml_spec['metadata']['namespace'], k8s_client.V1DeleteOptions())
    except k8s_client.rest.ApiException as e:
      logging.exception('Exception when calling CoreV1Api->delete_namespaced_pod: {}\n'.format(str(e)))

  def _read_pod_log(self, pod_name, yaml_spec):
    try:
      api_response = self._corev1.read_namespaced_pod_log(pod_name, yaml_spec['metadata']['namespace'])
    except k8s_client.rest.ApiException as e:
      logging.exception('Exception when calling CoreV1Api->read_namespaced_pod_log: {}\n'.format(str(e)))
      return False
    return api_response

  def run_job(self, yaml_spec, timeout=600):
    """ run_job runs a kubernetes job and clean up afterwards """
    pod_name, succ = self._create_k8s_job(yaml_spec)
    if not succ:
      return False
    # timeout in seconds
    succ = self._wait_for_k8s_job(pod_name, yaml_spec, timeout)
    if not succ:
      logging.info('Kubernetes job failed.')
      return False
    #TODO: investigate the read log error
    # print(self._read_pod_log(pod_name, yaml_spec))
    self._delete_k8s_job(pod_name, yaml_spec)
    return succ
