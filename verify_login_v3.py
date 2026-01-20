import pexpect
import sys
import time

def try_login(username, password):
    print(f"\n>>> Attempting login for '{username}'...")
    # 5 minute timeout for boot completion
    child = pexpect.spawn(f'virtctl console web-01 -n vm-opasnet', timeout=300)
    child.logfile_read = sys.stdout.buffer
    
    try:
        # Refresh prompt
        child.sendline('')
        
        # Wait for login prompt specifically
        child.expect(['login:', 'web-01 login:'], timeout=240)
        print(f"\nFound login prompt for {username}")
        
        child.sendline(username)
        child.expect('Password:', timeout=20)
        child.sendline(password)
        
        # Check result
        result = child.expect(['Login incorrect', f'{username}@web-01', '\\$'], timeout=30)
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
    if try_login('admin', 'admin'):
        sys.exit(0)
    else:
        print("\nLogin attempt failed.")
        sys.exit(1)
