from anthropic import Anthropic
import sys
import os
from dotenv import load_dotenv

load_dotenv()
try:
    client = Anthropic()
    client.messages.create(model='claude-3-opus-20240229', max_tokens=10, messages=[{'role':'user', 'content':'hi'}])
    print("SUCCESS")
except Exception as e:
    import json
    if hasattr(e, 'response'):
        print(json.dumps(e.response.json(), indent=2))
    else:
        print(str(e))
