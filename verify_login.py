import pexpect
import sys

def verify_login():
    print("Attempting to verify login for web-01...")
    # Increase timeout as boot might take time
    child = pexpect.spawn('virtctl console web-01 -n vm-opasnet', timeout=180)
    child.logfile_read = sys.stdout.buffer
    
    try:
        # Send enters to refresh prompt
        for _ in range(3):
            child.sendline('')
        
        # Wait for login prompt
        child.expect(['login:', 'web-01 login:'], timeout=120)
        print("\nFound login prompt.")
        
        child.sendline('admin')
        child.expect('Password:', timeout=20)
        child.sendline('admin')
        
        # Check for bash prompt
        child.expect(['admin@web-01', '\\$'], timeout=30)
        print("\n[SUCCESS] Login verified successfully!")
        
        # Clean exit
        child.sendline('logout')
        return True
    except Exception as e:
        print(f"\n[FAILURE] Login verification failed: {e}")
        # Capture some context
        print("Last recorded output before failure:")
        print(child.before.decode('utf-8', errors='ignore') if hasattr(child, 'before') else "N/A")
        return False

if __name__ == "__main__":
    if verify_login():
        sys.exit(0)
    else:
        sys.exit(1)
