import pexpect
import sys

def debug_web01():
    print("Debugging web-01 IP assignment...")
    child = pexpect.spawn('virtctl console web-01 -n vm-opasnet', timeout=60)
    
    try:
        child.sendline('')
        # Expect login prompt
        idx = child.expect(['login:', 'web-01 login:', 'core@web-01', '\\$'], timeout=30)
        
        if idx in [0, 1]:
            child.sendline('core')
            child.expect('Password:', timeout=10)
            child.sendline('core')
            child.expect(['core@web-01', '\\$'], timeout=20)
        
        print("Logged in. Trying manual IP assignment...")
        
        # Check current state
        child.sendline('ip addr show enp1s0')
        child.expect(['core@web-01', '\\$'], timeout=10)
        print("Current State:")
        print(child.before.decode())
        
        # Try the command
        cmd = "sudo ip addr add 10.215.100.101/24 dev enp1s0"
        print(f"Running: {cmd}")
        child.sendline(cmd)
        child.expect(['core@web-01', '\\$'], timeout=10)
        print("Output:")
        print(child.before.decode())
        
        # Check if it stuck
        child.sendline('ip addr show enp1s0')
        child.expect(['core@web-01', '\\$'], timeout=10)
        print("New State:")
        print(child.before.decode())
        
        child.sendline('logout')
        
    except Exception as e:
        print(f"Error: {e}")
        try:
             print("Buffer:", child.before.decode())
        except: pass

if __name__ == "__main__":
    debug_web01()
