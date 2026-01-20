import pexpect
import sys
import time

def extract_detailed_info():
    print("Logging in as root for detailed diagnostics...")
    child = pexpect.spawn('virtctl console web-01 -n vm-opasnet', timeout=60)
    child.logfile = open('/tmp/pexpect_debug.log', 'wb')
    
    try:
        child.sendline('')
        child.expect(['login:', 'web-01 login:'], timeout=30)
        child.sendline('root')
        child.expect('Password:', timeout=10)
        child.sendline('admin')
        
        child.expect(['root@web-01', '#'], timeout=20)
        
        # 1. List users
        print("Checking /etc/passwd...")
        child.sendline('cat /etc/passwd | tail -n 10')
        child.expect(['root@web-01', '#'], timeout=10)
        
        # 2. Check cloud-init status
        print("Checking cloud-init status...")
        child.sendline('cloud-init status --long')
        child.expect(['root@web-01', '#'], timeout=10)
        
        # 3. Check for errors in the logs
        print("Searching for errors in cloud-init logs...")
        child.sendline('grep -i "error\|fail" /var/log/cloud-init.log | tail -n 20')
        child.expect(['root@web-01', '#'], timeout=10)
        
        # 4. Try setting admin password manually to see if it works
        print("Attempting manual password reset for admin...")
        child.sendline('echo "admin:admin" | chpasswd')
        child.expect(['root@web-01', '#'], timeout=10)
        
        # 5. Check if we can switch to admin
        print("Checking if 'su - admin' works...")
        child.sendline('su - admin -c "whoami && pwd"')
        child.expect(['root@web-01', '#'], timeout=10)
        
        child.sendline('logout')
        print("Done.")
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    extract_detailed_info()
