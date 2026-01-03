import requests
import sys

# The uvicorn server is running on port 8001
BASE_URL = "http://0.0.0.0:8001/apps"

def test_create_app(repo_url, expected_status):
    print(f"Testing URL: {repo_url}")
    try:
        response = requests.post(BASE_URL, json={"repo_url": repo_url})
        print(f"Status Code: {response.status_code}")
        if response.status_code == expected_status:
            print("✅ PASSED")
            return True
        else:
            print(f"❌ FAILED: Expected {expected_status}, got {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ FAILED: Could not connect to server. Is it running?")
        return False

def main():
    print("Starting verification...")
    
    # 1. Valid URL
    if not test_create_app("https://github.com/fastapi/fastapi", 201):
        sys.exit(1)
        
    # 2. Invalid URL (Non-existent repo)
    if not test_create_app("https://github.com/fastapi/non-existent-repo-12345", 400):
        sys.exit(1)

    # 3. Invalid URL (Bad Format)
    if not test_create_app("https://google.com", 400):
        sys.exit(1)

    print("All tests passed!")

if __name__ == "__main__":
    main()
