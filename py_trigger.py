import subprocess, requests, time, os, zipfile, io

# --- CONFIG ---
TOKEN = os.getenv("GH_BUILD_TOKEN") 
if not TOKEN:
    print("❌ Error: GH_BUILD_TOKEN environment variable not found!")
    exit()
REPO = "OmarMustafa-SwiftAct/remote-build-test"
USER_ID = "Omar" # Change to differentiate teammates
HEADERS = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github.v3+json"}

def run_git(args):
    return subprocess.run(args, capture_output=True, text=True)

def trigger_shadow_build():
    shadow = f"build-shadow/{USER_ID}"
    print(f"📦 Creating shadow branch: {shadow}")
    
    # 1. Shadow Push (The "Trick")
    run_git(["git", "checkout", "-b", shadow])
    run_git(["git", "add", "."])
    run_git(["git", "commit", "-m", "Remote build trigger"])
    run_git(["git", "push", "origin", shadow, "--force"])
    
    # 2. Trigger API
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/build.yml/dispatches"
    requests.post(url, headers=HEADERS, json={"ref": shadow})
    
    # 3. Local Cleanup
    run_git(["git", "checkout", "-"])
    run_git(["git", "branch", "-D", shadow])
    print("🚀 Build triggered! Polling for results...")
    poll_for_artifact()

def poll_for_artifact():
    while True:
        # Get latest run
        url = f"https://api.github.com/repos/{REPO}/actions/runs?per_page=1"
        run = requests.get(url, headers=HEADERS).json()["workflow_runs"][0]
        
        if run["status"] == "completed":
            print(f"✅ Build {run['conclusion']}!")
            if run["conclusion"] == "success":
                download(run["id"])
            break
        time.sleep(5)

def download(run_id):
    url = f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}/artifacts"
    art = requests.get(url, headers=HEADERS).json()["artifacts"][0]
    r = requests.get(art["archive_download_url"], headers=HEADERS)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        z.extractall("./output")
    print("🎉 Done! Check the /output folder.")

if __name__ == "__main__":
    trigger_shadow_build()