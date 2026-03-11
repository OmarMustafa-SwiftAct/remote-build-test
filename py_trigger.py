import os
import subprocess
import requests
import time
import zipfile
import io

# --- CONFIG ---
REPO = "OmarMustafa-SwiftAct/remote-build-test"
TOKEN_VAR_NAME = "GH_BUILD_TOKEN"
USER_ID = os.getlogin()
SHADOW_BRANCH = f"build/{USER_ID}"

def get_valid_token():
    token = os.getenv(TOKEN_VAR_NAME)
    
    # Check if token exists and is valid
    if not token or not is_token_valid(token):
        print(f"{TOKEN_VAR_NAME} is missing, expired, or invalid.")
        token = input("Please enter a valid GitHub Personal Access Token: ").strip()
        
        # Save it permanently to Windows User Environment Variables
        subprocess.run(["setx", TOKEN_VAR_NAME, token], capture_output=True)
        print(f"Token saved! (You may need to restart your terminal/IDE for this to take effect globally).")
        
        # For the current running process, update the env
        os.environ[TOKEN_VAR_NAME] = token
        
    return token

def is_token_valid(token):
    """Test if the token can actually talk to the GitHub API"""
    headers = {"Authorization": f"token {token}"}
    response = requests.get("https://api.github.com/user", headers=headers)
    return response.status_code == 200

def trigger_and_download():
    token = get_valid_token()
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}

    # 1. Trigger via Git Push (No token needed for Push if using SSH/Credential Manager)
    print(f"Pushing code to {SHADOW_BRANCH}...")
    subprocess.run(["git", "checkout", "-B", SHADOW_BRANCH], check=True)
    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "commit", "-m", "Remote build", "--allow-empty"], check=True)
    subprocess.run(["git", "push", "origin", SHADOW_BRANCH, "--force"], check=True)
    subprocess.run(["git", "checkout", "-"], check=True)

    # 2. Poll GitHub for the Build Result
    print("Build started! Polling GitHub for completion...")
    run_id = None
    while not run_id:
        runs = requests.get(f"https://api.github.com/repos/{REPO}/actions/runs", headers=headers).json()
        for run in runs.get("workflow_runs", []):
            if run["head_branch"] == SHADOW_BRANCH and run["status"] != "completed":
                run_id = run["id"]
                break
        time.sleep(5)

    while True:
        run_data = requests.get(f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}", headers=headers).json()
        if run_data["status"] == "completed":
            print(f"Build {run_data['conclusion']}!")
            if run_data["conclusion"] == "success":
                download_artifact(run_id, headers)
            break
        time.sleep(5)

def download_artifact(run_id, headers):
    url = f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}/artifacts"
    artifacts = requests.get(url, headers=headers).json()
    
    if artifacts["total_count"] > 0:
        download_url = artifacts["artifacts"][0]["archive_download_url"]
        print("Downloading HEX result...")
        r = requests.get(download_url, headers=headers)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            z.extractall("./output")
            print("Success! Files saved to ./output folder.")

if __name__ == "__main__":
    trigger_and_download()