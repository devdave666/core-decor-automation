"""
Run this any time to check whether the Amazon Creators API has unblocked
for this account yet (needs 10 qualifying Associates sales in the past 30
days -- see amazon_creators.py's module docstring). Prints a clear
eligible/not-yet result and exits non-zero only on a genuine unexpected
error, not on the expected AssociateNotEligible case, so this is safe to
run as a periodic check without treating "not yet" as a failure.
"""
import os
import sys

from amazon_creators import AmazonCreatorsError, get_access_token, search_items


def main():
    client_id = os.environ["AMAZON_CREATORS_CREDENTIAL_ID"]
    client_secret = os.environ["AMAZON_CREATORS_SECRET"]
    partner_tag = os.environ["AMAZON_ASSOCIATE_TAG"]

    print("Requesting access token...")
    token = get_access_token(client_id, client_secret)
    print("Token OK. Trying a real SearchItems call...")

    try:
        result = search_items(token, keywords="brass pendant light", partner_tag=partner_tag)
        print("\n*** ELIGIBLE *** SearchItems succeeded.")
        print(f"Returned {len(result.get('items', []))} item(s). The full automated pipeline can be built now.")
    except AmazonCreatorsError as e:
        if e.reason == "AssociateNotEligible":
            print("\nNot eligible yet (AssociateNotEligible) -- needs 10 qualifying "
                  "Associates sales in the past 30 days. This is expected, not an error.")
            return
        print(f"\nUnexpected Creators API error (reason={e.reason}, http={e.http_status}): {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
