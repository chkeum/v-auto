import pexpect
import sys
import time

def extract_logs():
    print("Attempting to log in as root to extract logs...")
    child = pexpect.spawn('virtctl console web-01 -n vm-opasnet', timeout=60)
    
    try:
        child.sendline('')
        child.expect(['login:', 'web-01 login:'], timeout=30)
        child.sendline('root')
        child.expect('Password:', timeout=10)
        child.sendline('admin')
        
        # Wait for prompt
        child.expect(['root@web-01', '#'], timeout=20)
        print("Logged in. Extracting logs...")
        
        # Check if admin user exists
        child.sendline('grep "^admin:" /etc/passwd')
        child.expect(['root@web-01', '#'], timeout=10)
        print("\n--- /etc/passwd check ---")
        print(child.before.decode())
        
        # Dump cloud-init output log
        child.sendline('cat /var/log/cloud-init-output.log')
        child.expect(['root@web-01', '#'], timeout=30)
        print("\n--- cloud-init-output.log ---")
        print(child.before.decode())
        
        # Check cloud-final status
        child.sendline('systemctl status cloud-final.service --no-pager')
        child.expect(['root@web-01', '#'], timeout=10)
        print("\n--- systemctl status cloud-final ---")
        print(child.before.decode())
        
        child.sendline('logout')
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    extract_logs()
