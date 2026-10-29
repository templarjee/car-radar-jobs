"""Temporary origin diagnostics: print selected non-secret claims, never the signed token."""
import base64
import json
from arval_db_sync import get_github_oidc
from run_catalog import api
token = get_github_oidc()
segment = token.split('.')[1]
claims = json.loads(base64.urlsafe_b64decode(segment + '=' * (-len(segment) % 4)))
keys = ('repository','repository_id','repository_owner_id','repository_visibility','ref','sub','workflow_ref','event_name','run_id','run_attempt')
print(json.dumps({k: claims.get(k) for k in keys}))
del token, segment, claims
print('Authenticated baseline:', api({'action':'baseline'}))
