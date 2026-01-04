import requests


owner = "abhishekabck"
repo = "Coursera"

url = f"https://api.github.com/repos/{owner}/{repo}"

response = requests.get(url)
if response.status_code == 200:
    data = response.json()
    if data.get("private"):
        print(f"The repository '{owner}/{repo}' is PRIVATE.")
    else:
        print(f"The repository '{owner}/{repo}' is PUBLIC.")
else:
    print(f"Error: {response.status_code} - {response.text}")
