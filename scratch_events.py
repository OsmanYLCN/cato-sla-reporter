import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('CATO_API_KEY')
account_id = int(os.getenv('CATO_ACCOUNT_ID', '0'))
endpoint = os.getenv('CATO_API_ENDPOINT', 'https://api.catonetworks.com/api/v1/graphql2')

headers = {'x-api-key': api_key, 'Content-Type': 'application/json'}
query = """
query GetEvents($accountID: ID!, $timeFrame: TimeFrame!) {
  events(
    accountID: $accountID
    timeFrame: $timeFrame
  ) {
    records {
      flatFields
    }
  }
}
"""
variables = {
    'accountID': account_id,
    'timeFrame': "last.P1D"
}

try:
    res = requests.post(endpoint, json={'query': query, 'variables': variables}, headers=headers)
    print("STATUS:", res.status_code)
    print("RESPONSE:", res.text[:1000])
except Exception as e:
    print("ERROR:", e)
