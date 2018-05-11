#
# Copyright (C) 2017 The Android Open Source Project
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
#

import json
import logging
import requests
import threading
import time

# Job status dict
JOB_STATUS_DICT = {
    # scheduled but not leased yet
    "ready": 0,
    # scheduled and in running
    "leased": 1,
    # completed job
    "complete": 2,
    # unexpected error during running
    "infra-err": 3,
    # never leased within schedule period
    "expired": 4,
    # device boot error after flashing the given img sets
    "bootup-err": 5
}


class VtiEndpointClient(object):
    """VTI (Vendor Test Infrastructure) endpoint client.

    Attributes:
        _headers: A dictionary, containing HTTP request header information.
        _url: string, the base URL of an endpoint API.
        _job: dict, currently leased job info.
    """

    def __init__(self, url):
        if url == "localhost":
            url = "http://localhost:8080/_ah/api/"
        else:
            if not url.startswith(("https://")) and not url.startswith("http://"):
                url = "https://" + url
            if url.endswith("appspot.com"):
                url += "/_ah/api/"
        self._headers = {"content-type": "application/json",
                   "Accept-Charset": "UTF-8"}
        self._url = url
        self._job = {}
        self._heartbeat_thread = None

    def UploadBuildInfo(self, builds):
        """Uploads the given build information to VTI.

        Args:
            builds: a list of dictionaries, containing info about all new
                    builds found.

        Returns:
            True if successful, False otherwise.
        """
        url = self._url + "build_info/v1/set"
        fail = False
        for build in builds:
            response = requests.post(url, data=json.dumps(build),
                                     headers=self._headers)
            if response.status_code != requests.codes.ok:
                logging.error("UploadBuildInfo error: %s", response)
                fail = True
        if fail:
            return False
        return True

    def UploadDeviceInfo(self, hostname, devices):
        """Uploads the given device information to VTI.

        Args:
            hostname: string, the hostname of a target host.
            devices: a list of dicts, containing info about all detected
                     devices that are attached to the host.

        Returns:
            True if successful, False otherwise.
        """
        url = self._url + "host_info/v1/set"
        payload = {}
        payload["hostname"] = hostname
        payload["devices"] = []
        for device in devices:
            new_device = {
                "serial": device["serial"],
                "product": device["product"],
                "status": device["status"]}
            payload["devices"].append(new_device)

        try:
            response = requests.post(url, data=json.dumps(payload),
                                     headers=self._headers)
        except requests.exceptions.ConnectionError as e:
            logging.exception(e)
            return False
        if response.status_code != requests.codes.ok:
            logging.error("UploadDeviceInfo error: %s", response)
            return False
        return True

    def UploadScheduleInfo(self, pbs, clear_schedule):
        """Uploads the given schedule information to VTI.

        Args:
            pbs: a list of dicts, containing info about all task schedules.
            clear_schedule: bool, True to clear all schedule data exist on the
                            scheduler

        Returns:
            True if successful, False otherwise.
        """
        if pbs is None or len(pbs) == 0:
            return False

        url = self._url + "schedule_info/v1/clear"
        succ = True
        if clear_schedule:
            response = requests.post(
                url, data=json.dumps({"manifest_branch": "na"}),
                headers=self._headers)
            if response.status_code != requests.codes.ok:
                logging.error("UploadScheduleInfo error: %s", response)
                succ = False

        if not succ:
            return False

        url = self._url + "schedule_info/v1/set"
        for pb in pbs:
            schedule = {}
            schedule["manifest_branch"] = pb.manifest_branch
            schedule["build_storage_type"] = pb.build_storage_type
            for build_target in pb.build_target:
                schedule["build_target"] = build_target.name
                schedule["require_signed_device_build"] = (
                    build_target.require_signed_device_build)
                for test_schedule in build_target.test_schedule:
                    schedule["test_name"] = test_schedule.test_name
                    schedule["period"] = test_schedule.period
                    schedule["priority"] = test_schedule.priority
                    schedule["device"] = []
                    schedule["device"].extend(test_schedule.device)
                    schedule["device_pab_account_id"] = pb.pab_account_id
                    schedule["shards"] = test_schedule.shards
                    schedule["param"] = test_schedule.param
                    schedule["retry_count"] = test_schedule.retry_count
                    schedule["gsi_storage_type"] = test_schedule.gsi_storage_type
                    schedule["gsi_branch"] = test_schedule.gsi_branch
                    schedule["gsi_build_target"] = test_schedule.gsi_build_target
                    schedule["gsi_pab_account_id"] = test_schedule.gsi_pab_account_id
                    schedule["gsi_vendor_version"] = test_schedule.gsi_vendor_version
                    schedule["test_storage_type"] = test_schedule.test_storage_type
                    schedule["test_branch"] = test_schedule.test_branch
                    schedule["test_build_target"] = test_schedule.test_build_target
                    schedule["test_pab_account_id"] = test_schedule.test_pab_account_id
                    response = requests.post(url, data=json.dumps(schedule),
                                             headers=self._headers)
                    if response.status_code != requests.codes.ok:
                        logging.error(
                            "UploadScheduleInfo error: %s", response)
                        succ = False
        return succ

    def UploadLabInfo(self, pbs, clear_labinfo):
        """Uploads the given lab information to VTI.

        Args:
            pbs: a list of dicts, containing info about all known labs.
            clear_labinfo: bool, True to clear all lab data exist on the
                           scheduler

        Returns:
            True if successful, False otherwise.
        """
        if pbs is None or len(pbs) == 0:
            return

        url = self._url + "lab_info/v1/clear"
        succ = True
        if clear_labinfo:
            response = requests.post(url, data=json.dumps({"name": "na"}),
                                     headers=self._headers)
            if response.status_code != requests.codes.ok:
                logging.error("UploadLabInfo error: %s", response)
                succ = False

        if not succ:
            return False

        url = self._url + "lab_info/v1/set"
        for pb in pbs:
            lab = {}
            lab["name"] = pb.name
            lab["owner"] = pb.owner
            lab["admin"] = []
            lab["admin"].extend(pb.admin)
            lab["host"] = []
            for host in pb.host:
                new_host = {}
                new_host["hostname"] = host.hostname
                new_host["ip"] = host.ip
                new_host["script"] = host.script
                new_host["device"] = []
                if host.device:
                    for device in host.device:
                        new_device = {}
                        new_device["serial"] = device.serial
                        new_device["product"] = device.product
                        new_host["device"].append(new_device)
                lab["host"].append(new_host)
            response = requests.post(url, data=json.dumps(lab),
                                     headers=self._headers)
            if response.status_code != requests.codes.ok:
                logging.error("UploadLabInfo error: %s", response)
                succ = False
        return succ

    def LeaseJob(self, hostname, execute=True):
        """Leases a job for the given host, 'hostname'.

        Args:
            hostname: string, the hostname of a target host.
            execute: boolean, True to lease and execute StartHeartbeat, which is
                     the case that the leased job will be executed on this
                     process's context.

        Returns:
            True if successful, False otherwise.
        """
        if not hostname:
            return None, {}

        url = self._url + "job_queue/v1/get"
        response = requests.post(url, data=json.dumps({"hostname": hostname}),
                                 headers=self._headers)
        if response.status_code != requests.codes.ok:
            logging.error("LeaseJob error: %s", response.status_code)
            return None, {}

        response_json = json.loads(response.text)
        if ("return_code" in response_json
                and response_json["return_code"] != "SUCCESS"):
            logging.error("LeaseJob error: %s", response_json)
            return None, {}

        if "jobs" not in response_json:
            logging.error(
                "LeaseJob jobs not found in response json %s", response.text)
            return None, {}

        jobs = response_json["jobs"]
        if jobs and len(jobs) > 0:
            for job in jobs:
                if execute == True:
                    self._job = job
                    self.StartHeartbeat("leased", 60)
                return job["test_name"].split("/")[0], job
        return None, {}

    def ExecuteJob(self, job):
        """Executes leased job passed from parent process.

        Args:
            job: dict, information the on leased job.

        Returns:
            a string which is path to a script file for onecmd().
            a dict contains info on the leased job, will be passed to onecmd().
        """
        logging.info("Job info : {}".format(json.dumps(job)))
        if job is not None:
            self._job = job
            self.StartHeartbeat("leased", 60)
            return job["test_name"].split("/")[0], job

        return None, {}

    def UpdateLeasedJobStatus(self, status, update_interval):
        """Updates the status of the leased job.

        Args:
            status: string, status value.
            update_interval: int, time between heartbeats in second.
        """
        if self._job is None:
            return

        url = self._url + "job_queue/v1/heartbeat"
        self._job["status"] = JOB_STATUS_DICT[status]

        thread = threading.currentThread()
        while getattr(thread, 'keep_running', True):
            response = requests.post(url, data=json.dumps(self._job),
                                     headers=self._headers)
            if response.status_code != requests.codes.ok:
                logging.error("UpdateLeasedJobStatus error: %s", response)
            time.sleep(update_interval)

    def StartHeartbeat(self, status="leased", update_interval=60):
        """Starts the hearbeat_thread.

        Args:
            status: string, status value.
            update_interval: int, time between heartbeats in second.
        """
        if (self._heartbeat_thread is None
                or hasattr(self._heartbeat_thread, 'keep_running')):
            self._heartbeat_thread = threading.Thread(
                target=self.UpdateLeasedJobStatus,
                args=(
                    status,
                    update_interval,
                ))
            self._heartbeat_thread.daemon = True
            self._heartbeat_thread.start()

    def StopHeartbeat(self, status="complete", infra_log_url=""):
        """Stops the hearbeat_thread and sets current job's status.

        Args:
            status: string, status value.
            infra_log_url: string, URL to the uploaded infra log.
        """
        self._heartbeat_thread.keep_running = False

        if self._job is None:
            return

        url = self._url + "job_queue/v1/heartbeat"
        self.SetJobStatusFromLeasedTo(status)
        self._job["infra_log_url"] = infra_log_url

        response = requests.post(
            url, data=json.dumps(self._job), headers=self._headers)
        if response.status_code != requests.codes.ok:
            logging.error("StopHeartbeat error: %s", response)

        self._job = None

    def SetJobStatusFromLeasedTo(self, status):
        """Sets current job's status only when the job's status is 'leased'.

        Args:
            status: string, status value.
        """
        if (self._job is not None and
            self._job["status"] == JOB_STATUS_DICT["leased"]):
            self._job["status"] = JOB_STATUS_DICT[status]

    def UploadHostVersion(self, hostname, vtslab_version):
        """Uploads vtslab version.

        Args:
            hostname: string, the name of the host.
            vtslab_version: string, current version of vtslab package.
        """
        url = self._url + "lab_info/v1/set_version"
        host = {}
        host["hostname"] = hostname
        host["vtslab_version"] = vtslab_version

        try:
            response = requests.post(url, data=json.dumps(host),
                                    headers=self._headers)
        except requests.exceptions.ConnectionError as e:
            logging.exception(e)
            return
        if response.status_code != requests.codes.ok:
            logging.error("UploadHostVersion error: %s", response)

    def CheckBootUpStatus(self):
        """Checks whether the device_img + gsi from the job fails to boot up.

        Returns:
            True if the devices flashed with the given imgs from the leased job
            succeed to boot up. False otherwise.
        """
        if self._job:
            return (self._job["status"] != JOB_STATUS_DICT["bootup-err"])
        return False

    def GetJobTestType(self):
        """Returns the test type of the leased job.

        Returns:
            int, test_type attr in the job message. 0 when there is no job
            leased to this vti_endpoint_client.
        """
        if self._job and "test_type" in self._job:
            try:
                return int(self._job["test_type"])
            except ValueError as e:
                logging.exception(e)
        return 0