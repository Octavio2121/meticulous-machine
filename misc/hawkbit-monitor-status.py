#!/usr/bin/env python3

import argparse
import requests
import attr
import json

class HawkbitError(Exception):
    pass

@attr.s(eq=False)
class HawkbitMgmtClient:
    host = attr.ib(validator=attr.validators.instance_of(str))
    port = attr.ib(validator=attr.validators.instance_of(int))
    username = attr.ib(default="admin", validator=attr.validators.instance_of(str))
    password = attr.ib(default="admin", validator=attr.validators.instance_of(str))

    def __attrs_post_init__(self):
        if self.port == 443:
            self.url = f"https://{self.host}:{self.port}/rest/v1/{{endpoint}}"
        else:
            self.url = f"http://{self.host}:{self.port}/rest/v1/{{endpoint}}"
        self.id = {}  # To store IDs for recent operations

    def get(self, endpoint: str):
        url = self.url.format(endpoint=endpoint)
        req = requests.get(
            url,
            headers={"Content-Type": "application/json;charset=UTF-8"},
            auth=(self.username, self.password),
        )
        if req.status_code != 200:
            raise HawkbitError(f"HTTP error {req.status_code}: {req.content.decode()}")
        return req.json()

    def post(self, endpoint: str, json_data: dict):
        url = self.url.format(endpoint=endpoint)
        req = requests.post(
            url,
            headers={"Content-Type": "application/json;charset=UTF-8"},
            auth=(self.username, self.password),
            json=json_data
        )
        if req.status_code not in [200, 201]:
            raise HawkbitError(f"HTTP error {req.status_code}: {req.content.decode()}")
        return req.json()

    def get_targets_by_filter(self, filter_query):
        return self.get(f"targets?q={filter_query}")

    def get_target_actions(self, target_id):
        return self.get(f"targets/{target_id}/actions?limit=10&sort=id:DESC")

    def get_action(self, action_id: str = None, target_id: str = None):
        action_id = action_id or self.id.get("action")
        target_id = target_id or self.id.get("target")
        if not action_id or not target_id:
            raise HawkbitError("Action ID or Target ID not provided and not available from recent operations")
        return self.get(f"targets/{target_id}/actions/{action_id}")

    def get_action_status(self, action_id: str = None, target_id: str = None):
        action_id = action_id or self.id.get("action")
        target_id = target_id or self.id.get("target")
        if not action_id or not target_id:
            raise HawkbitError("Action ID or Target ID not provided and not available from recent operations")
        req = self.get(f"targets/{target_id}/actions/{action_id}/status?offset=0&limit=50&sort=id:DESC")
        return req.get("content", [])

    def assign_distribution(self, target_id, distribution_id):
        endpoint = f"targets/{target_id}/assignedDS"
        data = [{
            "id": distribution_id,
            "type": "forced"
        }]
        return self.post(endpoint, data)

    def get_latest_distribution(self):
        distributions = self.get("distributionsets?sort=createdAt:DESC&limit=1")
        if distributions and 'content' in distributions and distributions['content']:
            return distributions['content'][0]
        raise HawkbitError("No available distributions found")

def get_recent_action_status(client, target_id):
    actions = client.get_target_actions(target_id)
    if actions and 'content' in actions:
        for action in actions['content']:
            action_id = action.get('id')
            status = action.get('status', 'Unknown')
            dist_set = action.get('distributionSet', {})
            dist_name = dist_set.get('name', 'Unknown')
            dist_version = dist_set.get('version', 'Unknown')
            
            action_status = client.get_action_status(action_id, target_id)
            
            detailed_status = "No detailed status available"
            if action_status:
                latest_status = action_status[0]  # Most recent status
                detailed_status = f"Type: {latest_status.get('type', 'Unknown')}, Status: {status}"
                if 'messages' in latest_status:
                    detailed_status += f", Message: {latest_status['messages'][0] if latest_status['messages'] else 'No message'}"
            
            return {
                "status": status,
                "distribution": f"{dist_name} ({dist_version})",
                "details": detailed_status
            }
    return None

def process_targets(client, channel):
    filter_query = f'attribute.update_channel=="{channel}"'
    targets = client.get_targets_by_filter(filter_query)
    targets_to_update = []

    print(f"Targets with channel '{channel}':")
    if isinstance(targets, dict) and 'content' in targets:
        for target in targets['content']:
            target_id = target.get('controllerId')
            target_name = target.get('name')
            action_status = get_recent_action_status(client, target_id)
            
            print(f"ID: {target_id}, Name: {target_name}")
            print(f"Status: {action_status}")
            print("--------------------")

            if action_status:
                details = action_status['details'].split(', ')
                action_type = next((d.split(': ')[1] for d in details if d.startswith('Type:')), None)
                message = next((d.split(': ')[1] for d in details if d.startswith('Message:')), None)

                if action_type != 'running' and not (action_status['status'] == 'finished' and message == 'Software bundle installed successfully.'):
                    targets_to_update.append(target_id)

    return targets_to_update

def reassign_distribution(client, targets, distribution_id):
    for target_id in targets:
        try:
            print(f"Attempting to reassign distribution {distribution_id} al target {target_id}")
            response = client.assign_distribution(target_id, distribution_id)
            print(f"Response from the assignment: {json.dumps(response, indent=2)}")
            print(f"Distribution reassigned to target: {target_id}")
        except HawkbitError as e:
            print(f"Error reassigning distribution to target {target_id}: {str(e)}")
            print("Error details:")
            print(e.args[0] if e.args else "No additional details available")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor and update Hawkbit targets")
    parser.add_argument("host", help="Hawkbit server")
    parser.add_argument("port", type=int, help="Hawkbit port")
    parser.add_argument("username", help="Hawkbit user")
    parser.add_argument("password", help="Hawkbit password")
    parser.add_argument("channel", help="Update channel (e.g., 'nightly')")

    args = parser.parse_args()

    client = HawkbitMgmtClient(
        args.host,
        args.port,
        username=args.username,
        password=args.password
    )

    try:
        latest_distribution = client.get_latest_distribution()
        distribution_id = latest_distribution['id']
        print(f"Latest distribution found: {latest_distribution['name']} (ID: {distribution_id})")

        targets_to_update = process_targets(client, args.channel)
        
        if targets_to_update:
            print("\nTargets that need updating:")
            for target_id in targets_to_update:
                print(target_id)
            
            reassign_distribution(client, targets_to_update, distribution_id)
        else:
            print("\nNo targets need updating.")
    except HawkbitError as e:
        print(f"Error: {str(e)}")
        print("Error details:")
        print(e.args[0] if e.args else "No additional details available")