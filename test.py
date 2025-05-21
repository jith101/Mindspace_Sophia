import requests
import re

# Import API key from config
from config.api_keys import RUNPOD_API_KEY

headers = {
    'Content-Type': 'application/json',
    'Authorization': RUNPOD_API_KEY
}



question = "I’ve been feeling empty and disconnected from everything, even the people I love. It’s like I’m just going through the motions, and I don’t know how to find meaning in anything anymore. What should I do?"
context = "I recently lost someone close to me, and since then, it’s like a part of me is missing. I’ve tried keeping busy, talking to friends, even going to the gym, but nothing feels real or fulfilling. I’m scared this numbness will never go away."


# This assumes the model expects `question` and `context`, not a raw prompt string
data = {
    'input': {
        "question": question,
        "context": context
    }
}

# Send the request
response = requests.post('https://api.runpod.ai/v2/ovzpgfqd38xtyh/runsync', headers=headers, json=data)
result = response.json()

# Get the full raw answer
raw_answer = result.get("output", {}).get("answer", "")


# Step 1: Extract everything after 'Answer: [/INST]'
answer_match = re.search(r'Answer:\s*\[/INST\]\s*(.*)', raw_answer, re.DOTALL)
if answer_match:
    extracted_text = answer_match.group(1).strip()

    # Step 2: Check for a 4-digit number and truncate at its position
    four_digit_match = re.search(r'\b\d{4}\b', extracted_text)
    if four_digit_match:
        cutoff_index = four_digit_match.start()
        cleaned_text = extracted_text[:cutoff_index].strip()
    else:
        cleaned_text = extracted_text.strip()

    print("\nCleaned Answer:\n", cleaned_text)

else:
    print("\nCould not extract text after 'Answer: [/INST]'.")
