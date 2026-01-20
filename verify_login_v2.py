import pexpect
import sys
import time

def try_login(username, password):
    print(f"\n>>> Attempting login for '{username}'...")
    child = pexpect.spawn(f'virtctl console web-01 -n vm-opasnet', timeout=60)
    child.logfile_read = sys.stdout.buffer
    
    try:
        # Refresh prompt
        child.sendline('')
        time.sleep(1)
        
        # Wait for prompt
        i = child.expect(['login:', 'Password:'], timeout=30)
        if i == 1: # Already at password prompt somehow?
             child.sendline(password)
        else:
             child.sendline(username)
             child.expect('Password:', timeout=10)
             child.sendline(password)
        
        # Check result
        result = child.expect(['Login incorrect', f'{username}@web-01', '\\$'], timeout=10)
        if result == 0:
            print(f"\n[X] Login failed for {username}")
            child.close(force=True)
            return False
        else:
            print(f"\n[V] LOGIN SUCCESSFUL for {username}!")
            child.sendline('logout')
            child.close(force=True)
            return True
            
    except Exception as e:
        print(f"\n[!] Error during login for {username}: {e}")
        child.close(force=True)
        return False

if __name__ == "__main__":
    success = False
    if try_login('admin', 'admin'):
        success = True
    elif try_login('suser', 'suser'):
        success = True
    
    if success:
        sys.exit(0)
    else:
        print("\nAll login attempts failed.")
        sys.exit(1)
