import os
import subprocess
import requests
import time
import zipfile
import io
import sys

# --- CONFIGURATION ---
REPO = "OmarMustafa-SwiftAct/remote-build-test"
TOKEN_VAR = "GH_BUILD_TOKEN"
USER_ID = os.getlogin().replace(" ", "-")
SHADOW_BRANCH = f"build/{USER_ID}"

POLL_INTERVAL = 5  # Seconds between API checks
TIMEOUT = 600      # 10 minute timeout

def run_git(args):
    """Executes git commands and returns output/success."""
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Git Error: {result.stderr.strip()}")
        return False, result.stdout
    return True, result.stdout

def get_token():
    """Checks for a valid token, prompts and saves if missing or expired."""
    token = os.getenv(TOKEN_VAR)
    
    # Validation check
    headers = {"Authorization": f"token {token}"} if token else {}
    valid = False
    if token:
        resp = requests.get("https://api.github.com/user", headers=headers)
        valid = resp.status_code == 200

    if not valid:
        print(f"GitHub Token ({TOKEN_VAR}) is missing, invalid, or expired.")
        token = input("Please enter a valid GitHub Personal Access Token: ").strip()
        # Save to Windows User environment variables permanently
        subprocess.run(["setx", TOKEN_VAR, token], capture_output=True)
        os.environ[TOKEN_VAR] = token
        print("Token saved. Note: Restart VS Code later to refresh global environment.")
    
    return token

def trigger_shadow_push():
    print(f"📦 Syncing local changes to {SHADOW_BRANCH}...")
    
    # 1. Save current branch name
    success, branch_name = run_git(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    original_branch = branch_name.strip()

    # 2. STASH your current uncommitted changes (keeps them safe)
    run_git(["git", "stash", "push", "-u", "-m", "temp_build_stash"])

    # 3. Create the shadow branch based on your CURRENT state
    run_git(["git", "checkout", "-B", SHADOW_BRANCH])
    
    # 4. Bring the changes into the shadow branch to push them
    run_git(["git", "stash", "apply"])
    run_git(["git", "add", "."])
    run_git(["git", "commit", "-m", "Remote Build Trigger", "--allow-empty"])
    
    print(f"📡 Pushing to origin...")
    run_git(["git", "push", "origin", SHADOW_BRANCH, "--force"])
    
    # 5. Switch back to your original branch
    run_git(["git", "checkout", original_branch])
    
    # 6. POP the changes back (restores your editor to EXACTLY how it was)
    run_git(["git", "stash", "pop"])
    
    # 7. Clean up local shadow
    run_git(["git", "branch", "-D", SHADOW_BRANCH])

    print(f"✅ Workspace restored. You are back on '{original_branch}' with all changes intact.")

    
def poll_and_download(token):
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    print("Waiting for GitHub to start the build...")
    run_id = None
    start_time = time.time()

    # Find the latest run for our shadow branch
    while not run_id and (time.time() - start_time < 60):
        resp = requests.get(f"https://api.github.com/repos/{REPO}/actions/runs", headers=headers).json()
        for run in resp.get("workflow_runs", []):
            if run["head_branch"] == SHADOW_BRANCH and run["status"] != "completed":
                run_id = run["id"]
                print(f"Build found! ID: {run_id}. Monitoring...")
                break
        time.sleep(3)

    if not run_id:
        print("Could not find the triggered build on GitHub.")
        return

    # Watch for completion
    while time.time() - start_time < TIMEOUT:
        run_data = requests.get(f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}", headers=headers).json()
        status = run_data["status"]
        conclusion = run_data["conclusion"]

        if status == "completed":
            print(f"Build finished with status: {conclusion}")
            if conclusion == "success":
                download_artifact(run_id, headers)
            else:
                print("Build failed. Check GitHub Actions logs for details.")
            break
        
        time.sleep(POLL_INTERVAL)

def download_artifact(run_id, headers):
    art_resp = requests.get(f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}/artifacts", headers=headers).json()
    
    if art_resp["total_count"] > 0:
        # We take the first artifact found
        artifact = art_resp["artifacts"][0]
        download_url = artifact["archive_download_url"]
        
        print(f"Downloading {artifact['name']}...")
        r = requests.get(download_url, headers=headers)
        
        if r.status_code == 200:
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                z.extractall("./build_output")
                print("Success! Result saved to the './build_output' folder.")
        else:
            print("Failed to download artifact.")
    else:
        print("No artifacts were found for this build.")

if __name__ == "__main__":
    try:
        # Ensure we are in a git repo
        if not os.path.exists(".git"):
            print("Error: You must run this script from the root of a Git repository.")
            sys.exit(1)
            
        current_token = get_token()
        trigger_shadow_push()
        poll_and_download(current_token)
    except KeyboardInterrupt:
        print("\nBuild monitoring cancelled by user.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")