import pexpect
import sys
import time

def try_login_once(username, password):
    print(f"\n>>> Trying login for '{username}'...")
    child = pexpect.spawn(f'virtctl console web-01 -n vm-opasnet', timeout=60)
    # child.logfile_read = sys.stdout.buffer
    
    try:
        child.sendline('')
        i = child.expect(['login:', 'web-01 login:'], timeout=30)
        child.sendline(username)
        child.expect('Password:', timeout=20)
        child.sendline(password)
        
        result = child.expect(['Login incorrect', f'{username}@web-01', '#', '\\$'], timeout=10)
        if result == 0:
            child.close(force=True)
            return False
        else:
            print(f"\n[V] SUCCESS: Logged in as {username}")
            child.sendline('logout')
            child.close(force=True)
            return True
    except Exception:
        child.close(force=True)
        return False

def verify_all():
    start_time = time.time()
    timeout = 600 # 10 minutes
    
    users = [('admin', 'admin'), ('ubuntu', 'admin'), ('root', 'admin')]
    
    print("Starting polling for login... (waiting for Cloud-init to finish)")
    
    while time.time() - start_time < timeout:
        for user, pwd in users:
            if try_login_once(user, pwd):
                return True
        print("Retrying in 10 seconds...")
        time.sleep(10)
    
    return False

if __name__ == "__main__":
    if verify_all():
        sys.exit(0)
    else:
        print("\nAll login attempts failed after 10 minutes.")
        sys.exit(1)
