import argparse
import json
from aisl_sdk import AislClient

p = argparse.ArgumentParser()
p.add_argument("--api-url", required=True)
p.add_argument("--system-id", required=True)
p.add_argument("--revision-id")
a = p.parse_args()

with AislClient(a.api_url) as client:
    revision = client.revision(a.system_id, a.revision_id) if a.revision_id else client.active_revision(a.system_id)
    print(json.dumps({
        "system_id": revision.system_id,
        "revision_id": revision.revision_id,
        "capabilities": list(revision.get_capabilities()),
        "products": [p.raw for p in revision.list_products()],
    }, ensure_ascii=False, indent=2))
