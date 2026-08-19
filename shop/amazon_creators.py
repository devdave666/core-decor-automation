"""
Amazon Creators API client -- the OAuth2 replacement for PA-API 5.0 (PA-API
itself is being retired May 15, 2026; Offers V1 goes first, January 31,
2026). Reusable pieces only: getting an access token and calling
SearchItems. NOT wired into any pipeline yet -- confirmed blocked as of
2026-08-18 by Amazon's own eligibility gate (AssociateNotEligible: fewer
than 10 qualifying Associates sales in the past 30 days). See
check_eligibility.py and llms.txt's "Amazon Creators API" section for the
full story before building anything further on top of this.

Credentials: AMAZON_CREATORS_CREDENTIAL_ID (client_id) and
AMAZON_CREATORS_SECRET (client_secret) as GitHub Actions secrets;
AMAZON_ASSOCIATE_TAG (partnerTag, not sensitive) as a repository variable.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://api.amazon.com/auth/o2/token"
SEARCH_URL = "https://creatorsapi.amazon/catalog/v1/searchItems"


class AmazonCreatorsError(Exception):
    def __init__(self, message, reason=None, http_status=None):
        super().__init__(message)
        self.reason = reason
        self.http_status = http_status


def get_access_token(client_id, client_secret):
    """Client-credentials grant. Tokens are valid 1 hour -- callers should
    cache and reuse within that window rather than fetching one per call."""
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "creatorsapi::default",
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL, data=data, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())["access_token"]
    except urllib.error.HTTPError as e:
        raise AmazonCreatorsError(
            f"Token request failed: {e.read().decode(errors='replace')}", http_status=e.code,
        )


def search_items(access_token, keywords, partner_tag, marketplace="www.amazon.com", item_count=5):
    """Raises AmazonCreatorsError with reason='AssociateNotEligible' when
    the account doesn't meet Amazon's sales threshold -- this is the
    expected failure mode until that clears, not a bug to work around."""
    body = json.dumps({
        "keywords": keywords,
        "partnerTag": partner_tag,
        "marketplace": marketplace,
        "itemCount": item_count,
    }).encode()
    req = urllib.request.Request(
        SEARCH_URL, data=body, method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "x-marketplace": marketplace,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode(errors="replace")
        try:
            reason = json.loads(error_body).get("reason")
        except json.JSONDecodeError:
            reason = None
        raise AmazonCreatorsError(f"SearchItems failed: {error_body}", reason=reason, http_status=e.code)
