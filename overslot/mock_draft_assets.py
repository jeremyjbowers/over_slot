"""
Query-string cache buster for mock draft static URLs on prod (S3/CDN).

Production uses fixed paths (no content hashes). Bump this when you ship
overslot/static/mock_draft/js/draft.js, data.js, or css/draft.css so browsers
and CDNs fetch fresh files. Keep in sync with MOCK_DRAFT_JS_VERSION in
draftboard/js/draft.js (and the copy under overslot/static/mock_draft/js/).
"""

MOCK_DRAFT_ASSET_VERSION = "2026-04-06.14"
