import pexpect
import sys
import time

def check_net():
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
        
        print("\n--- cat /etc/netplan/*.yaml ---")
        child.sendline('cat /etc/netplan/*.yaml')
        child.expect(['core@web-01', '\\$'], timeout=10)
        print(child.before.decode())
        
        print("\n--- cloud-init log errors ---")
        child.sendline('sudo grep -i "network" /var/log/cloud-init.log | tail -n 20')
        child.expect(['Password:', 'core@web-01', '\\$'], timeout=10)
        child.sendline('core')
        child.expect(['core@web-01', '\\$'], timeout=20)
        print(child.before.decode())
        
        child.sendline('logout')
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    check_net()
