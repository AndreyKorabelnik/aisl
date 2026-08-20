import argparse
from aisl_sdk import AislClient

p = argparse.ArgumentParser()
p.add_argument("--api-url", required=True)
a = p.parse_args()

with AislClient(a.api_url) as client:
    for system in client.list_systems():
        print(system.system_id, system.active_revision_id)
