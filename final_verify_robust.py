import pexpect
import sys
import time

def verify_session(username, password):
    print(f"\n>>> Verifying {username}...")
    # 5 minute timeout for boot
    child = pexpect.spawn(f'virtctl console web-01 -n vm-opasnet', timeout=300)
    # child.logfile_read = sys.stdout.buffer
    
    try:
        child.sendline('')
        # Expect login prompt or shell after potential network wait
        i = child.expect(['login:', f'{username}@web-01'], timeout=240)
        
        if i == 0:
            child.sendline(username)
            child.expect('Password:', timeout=20)
            child.sendline(password)
            child.expect([f'{username}@web-01', '\\$'], timeout=30)
        
        print(f"[V] {username} login successful.")
        
        # Check IP
        print(f"Checking IP for {username}...")
        child.sendline('ip -4 addr show enp1s0')
        # We expect 10.215.100.101
        idx = child.expect(['10.215.100.101', f'{username}@web-01'], timeout=20)
        
        if idx == 0:
            print("[V] IP 10.215.100.101 verified on enp1s0.")
            success = True
        else:
            print("[X] IP 10.215.100.101 NOT FOUND on enp1s0.")
            success = False
            
        child.sendline('logout')
        child.close(force=True)
        return success
    except Exception as e:
        print(f"[X] {username} verification failed: {e}")
        child.close(force=True)
        return False

if __name__ == "__main__":
    # Give it a bit more time for the previous boot attempt
    success = False
    for attempt in range(3):
        print(f"Verification attempt {attempt+1}...")
        if verify_session('core', 'core'):
            success = True
            break
        print("Waiting 30 seconds before retry...")
        time.sleep(30)
        
    if success:
        sys.exit(0)
    else:
        sys.exit(1)
