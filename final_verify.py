import pexpect
import sys
import time

def verify_session(username, password):
    print(f"\n>>> Verifying {username}...")
    child = pexpect.spawn(f'virtctl console web-01 -n vm-opasnet', timeout=60)
    
    try:
        child.sendline('')
        # Expect login prompt or shell
        i = child.expect(['login:', f'{username}@web-01'], timeout=45)
        
        if i == 0:
            child.sendline(username)
            child.expect('Password:', timeout=20)
            child.sendline(password)
            child.expect([f'{username}@web-01', '\\$'], timeout=30)
        
        print(f"[V] {username} login successful.")
        
        # Check IP
        print(f"Checking IP for {username}...")
        child.sendline('ip -4 addr show enp1s0')
        idx = child.expect(['inet 10.215.100.101', 'root@web-01', f'{username}@web-01'], timeout=10)
        
        if idx == 0:
            print("[V] IP 10.215.100.101 verified on enp1s0.")
            success = True
        else:
            print("[X] IP 10.215.100.101 NOT FOUND on enp1s0.")
            print("Output was:")
            print(child.before.decode())
            success = False
            
        child.sendline('logout')
        child.close(force=True)
        return success
    except Exception as e:
        print(f"[X] {username} verification failed: {e}")
        child.close(force=True)
        return False

if __name__ == "__main__":
    time.sleep(120) # Wait for boot
    v1 = verify_session('core', 'core')
    v2 = verify_session('suser', 'suser')
    if v1 and v2:
        sys.exit(0)
    else:
        sys.exit(1)
