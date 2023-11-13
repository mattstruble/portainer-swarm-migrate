import requests
import configparser
import json
import time
import logging
import sys
from packaging import version

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger(__file__)

class PortainerAPIError(Exception):
    def __init__(self, code, text, *args):
        super().__init__(args)
        self.code = code

        content = json.loads(text)

        self.message = content["message"]
        self.details = content["details"]

    def __str__(self):
        return f"Portainer API returned error code {self.code}: {self.message}\n{self.details}"


class PortainerAPI:
    url: str
    jwt: str

    def __init__(self, parser: configparser.ConfigParser):
        self.url = parser.get(section="portainer", option="url").strip()

        headers = {
            "Content-Type": "application/json"
        }

        data = {
            "Username": parser.get(section="portainer", option="username").strip(),
            "Password": parser.get(section="portainer", option="password").strip()
        }

        response = requests.post(f"{self.url}/api/auth", headers=headers, data=json.dumps(data))
        self._validate_response(response)

        self.jwt = json.loads(response.text)["jwt"]
        self.get_version_number()

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.jwt}",
                "Content-Type": "application/json"}

    @staticmethod
    def _validate_response(response):
        if response.status_code != 200:
            raise PortainerAPIError(response.status_code, response.text)
        logger.debug("Response text:" + response.text)

    def _get(self, url, **kwargs):
        response = requests.get(url, headers=self.headers, **kwargs)
        self._validate_response(response)
        return response

    def _post(self, url, **kwargs):
        response = requests.post(url, headers=self.headers, **kwargs)
        self._validate_response(response)
        return response

    def get_version_number(self):
        """There are changes in the api after certain versions"""
        response = self._get(f"{self.url}/api/system/version")
        self._version = json.loads(response.text)["ServerVersion"]

    def get_stacks(self) -> list:
        response = self._get(f"{self.url}/api/stacks")
        return json.loads(response.text)

    def start_stack(self, stack: dict):
        logger.debug(f"Starting: {stack['Name']}")

        base_uri = f"{self.url}/api/stacks/{stack['Id']}/start"
        if version.parse(self._version) >= version.parse("2.19.0"):
            query = f"?endpointId={stack['EndpointId']}"
            self._post(f"{base_uri}{query}")
        else:
            self._post(base_uri)

    def stop_stack(self, stack: dict):
        logger.debug(f"Stopping: {stack['Name']}")
        try:
            base_uri = f"{self.url}/api/stacks/{stack['Id']}/stop"
            if version.parse(self._version) >= version.parse("2.19.0"):
                query = f"?endpointId={stack['EndpointId']}"
                self._post(f"{base_uri}{query}")
            else:
                self._post(base_uri)
        except PortainerAPIError as api_error:
            if api_error.code == 400 and api_error.message == "Stack is already inactive":
                print(api_error.message)
            else:
                raise api_error

    def migrate_stack(self, stack: dict, new_swarm_id: str):
        logger.info(f"Migrating: {stack['Name']}")

        if stack["SwarmId"] == new_swarm_id:
            print("Stack already exists on the new swarm.")
            return

        data = {
            "endpointID": stack["EndpointId"],
            "name": stack["Name"],
            "swarmID": new_swarm_id
        }

        self._post(f"{self.url}/api/stacks/{stack['Id']}/migrate", data=json.dumps(data))

    def __repr__(self):
        return str({
            "url": self.url,
            "jwt": self.jwt
        })


def get_old_cluster_stacks(api: PortainerAPI, new_cluster_id: str) -> list:
    return [s for s in api.get_stacks() if s["SwarmId"] != new_cluster_id]


if __name__=="__main__":
    parser = configparser.ConfigParser()
    parser.read("configuration.cfg")

    api = PortainerAPI(parser)

    new_cluster_id = parser.get("swarm", "clusterID").strip()

    old_stacks = get_old_cluster_stacks(api, new_cluster_id)

    if len(old_stacks) == 0:
        logger.info("Could not find any orphaned stacks.")
        exit(0)

    logger.info(f"Found {len(old_stacks)} orphaned stacks. Beginning migration.")

    # Stop all old running stacks before migrating
    for stack in old_stacks:
        api.stop_stack(stack)

    # Wait for all the stacks to stop before trying to migrate them
    start_time = time.time()
    all_stopped = False
    while time.time() - start_time < 10:
        time.sleep(1)

        running = [s['Name'] for s in get_old_cluster_stacks(api, new_cluster_id) if s['Status'] == 1]

        if len(running) == 0:
            break

        for stack in running:
            logger.info(f"Couldn't stop '{stack['Name']}' retrying..")
            api.stop_stack(stack)

    if not all_stopped:
        running = [s['Name'] for s in get_old_cluster_stacks(api, new_cluster_id) if s['Status'] == 1]
        running_list = '\n\t'.join(running)
        logger.error(f"The following stacks could not be stopped and will need to be killed in the Docker CLI by running `sudo docker rm STACK_NAME`: {running_list}")
        exit(1)

    # Migrate old stacks
    for stack in old_stacks:
        api.migrate_stack(stack, parser.get("swarm", "clusterID").strip())
        time.sleep(0.5)
        api.start_stack(stack)
