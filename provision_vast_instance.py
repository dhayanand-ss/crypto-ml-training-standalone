import os
import sys
import subprocess
import json
import time

def get_vastai_path():
    # Find vastai executable
    scripts_dir = os.path.join(os.path.dirname(sys.executable), 'Scripts')
    vastai_path = os.path.join(scripts_dir, 'vastai.exe')
    if os.path.exists(vastai_path):
        return vastai_path
    
    # Fallback to just 'vastai' if not found (maybe in PATH)
    return 'vastai'

def run_vastai_command(args):
    vastai_exe = get_vastai_path()
    if vastai_exe == 'vastai':
        # If we rely on PATH, we might need shell=True on Windows if it's a bat/cmd
        # But let's try shell=False first with list
        cmd = [vastai_exe] + args
        try:
            result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"Error running command: {' '.join(cmd)}")
            print(f"Stdout: {e.stdout}")
            print(f"Stderr: {e.stderr}")
            return None
    else:
        # We have absolute path to exe, can use shell=False safely
        cmd = [vastai_exe] + args
        try:
            result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"Error running command: {' '.join(cmd)}")
            print(f"Stdout: {e.stdout}")
            print(f"Stderr: {e.stderr}")
            return None

def main():
    print("Starting Vast AI Provisioning...")
    
    # 1. Install vastai (pip is usually in path)
    print("Installing vastai...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "vastai"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        print("Failed to install vastai")
        print(e.stderr)
    
    # 2. Set API Key
    api_key = os.getenv("VASTAI_API_KEY")
    if not api_key:
        try:
            with open(".env", "r") as f:
                for line in f:
                    if line.startswith("VASTAI_API_KEY="):
                        api_key = line.split("=")[1].strip()
                        break
        except Exception:
            pass
            
    if not api_key:
        print("Error: VASTAI_API_KEY not found")
        sys.exit(1)
        
    print(f"Setting API Key: {api_key[:5]}...")
    run_vastai_command(["set", "api-key", api_key])
    
    # 3. Search for offers
    print("Searching for GPU offers...")
    # Using list args avoids quoting hell
    offers_json = run_vastai_command(["search", "offers", "gpu_total_ram>=11 disk_space>=30 verified=True datacenter=True", "--raw"])
    
    if not offers_json:
        print("Failed to search offers")
        sys.exit(1)
        
    try:
        offers = json.loads(offers_json)
    except json.JSONDecodeError:
        print("Failed to parse offers JSON")
        # print(offers_json) # Too verbose
        sys.exit(1)
        
    valid_offers = [o for o in offers if o.get('rentable', False)]
    if not valid_offers:
        print("No rentable offers found")
        sys.exit(1)
        
    valid_offers.sort(key=lambda x: float(x.get('dph_total', 100)))
    
    best_offer = valid_offers[0]
    offer_id = str(best_offer['id'])
    price = best_offer['dph_total']
    gpu_name = best_offer.get('gpu_name', 'Unknown')
    
    print(f"Selected Offer ID: {offer_id}")
    print(f"GPU: {gpu_name}")
    print(f"Price: ${price}/hr")
    
    # 4. Create Instance
    print("Creating instance...")
    
    repo_url = os.getenv("VASTAI_GITHUB_REPO", "https://github.com/dhayanand-ss/crypto-ml-training-standalone.git")
    repo_branch = os.getenv("VASTAI_GITHUB_BRANCH", "main")
    
    # Construct onstart command (run in Linux shell)
    onstart_cmd = (
        f"set -e && "
        f"cd /workspace && "
        f"[ ! -d crypto-ml-training-standalone ] && git clone -b {repo_branch} {repo_url} crypto-ml-training-standalone || true && "
        f"cd crypto-ml-training-standalone && "
        f"pip install -q -r requirements.txt && "
        f"python -m utils.trainer.trl_train --coin BTCUSDT --epochs 10 --batch_size 4 "
        f"--lora_rank 4 --window_hours 12 --threshold 0.005 --clip_eps 0.2 --kl_coef 0.1 --lr 2e-5"
    )
    
    
    # Debug: Print arguments before calling
    debug_args = ["create", "instance", offer_id, "--image", "pytorch/pytorch:latest", "--disk", "30", "--ssh", "--on-demand", "--onstart", onstart_cmd]
    print(f"DEBUG: calling run_vastai_command with args: {debug_args}")

    result = run_vastai_command(debug_args)
    
    if result:
        print("Instance creation output:")
        print(result)
        
        try:
            res_obj = json.loads(result)
            if res_obj.get('success'):
                new_id = str(res_obj.get('new_contract'))
                print(f"\nSUCCESS! Instance created with ID: {new_id}")
                
                # Wait and check status
                print("\nWaiting 10 seconds to check status...")
                time.sleep(10)
                status = run_vastai_command(["show", "instance", new_id])
                print(status)
            else:
                print("Creation failed according to API response")
        except:
            print("Could not parse creation response")
            
    else:
        print("Instance creation failed.")

if __name__ == "__main__":
    main()
