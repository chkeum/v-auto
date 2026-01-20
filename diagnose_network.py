import pexpect
import sys
import time

def diagnose_network():
    print("Logging in to diagnose network...")
    child = pexpect.spawn('virtctl console web-01 -n vm-opasnet', timeout=60)
    
    try:
        child.sendline('')
        child.expect(['login:', 'web-01 login:'], timeout=30)
        child.sendline('core')
        child.expect('Password:', timeout=10)
        child.sendline('core')
        
        child.expect(['core@web-01', '\\$'], timeout=20)
        
        print("\n--- ip addr ---")
        child.sendline('ip addr')
        child.expect(['core@web-01', '\\$'], timeout=10)
        print(child.before.decode())
        
        print("\n--- ls /etc/netplan ---")
        child.sendline('ls -l /etc/netplan')
        child.expect(['core@web-01', '\\$'], timeout=10)
        print(child.before.decode())
        
        print("\n--- cloud-init status ---")
        child.sendline('cloud-init status --long')
        child.expect(['core@web-01', '\\$'], timeout=10)
        print(child.before.decode())
        
        child.sendline('logout')
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    diagnose_network()
