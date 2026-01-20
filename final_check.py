import pexpect
import sys
import time

def verify(username, password):
    print(f"Verifying {username}...")
    child = pexpect.spawn(f'virtctl console web-01 -n vm-opasnet', timeout=60)
    # child.logfile_read = sys.stdout.buffer
    
    try:
        # Refresh and expect either login prompt OR existing shell
        child.sendline('')
        i = child.expect(['login:', f'{username}@web-01', '#', '\\$'], timeout=30)
        
        if i == 0: # login prompt
            child.sendline(username)
            child.expect('Password:', timeout=20)
            child.sendline(password)
            child.expect([f'{username}@web-01', '#', '\\$'], timeout=20)
        
        print(f"[V] {username} verified.")
        child.sendline('logout')
        child.close(force=True)
        return True
    except Exception as e:
        print(f"[X] {username} verification failed: {e}")
        child.close(force=True)
        return False

if __name__ == "__main__":
    v1 = verify('opas-admin', 'admin')
    v2 = verify('root', 'admin')
    if v1 and v2:
        sys.exit(0)
    else:
        sys.exit(1)
