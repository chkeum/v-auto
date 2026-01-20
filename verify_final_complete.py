import pexpect
import sys
import time

def verify_vm(vm_name, users_creds, expected_ips):
    print(f"\n>>>> Verifying {vm_name} <<<<")
    success = True
    
    # Wait for the VM to be ready for console
    child = pexpect.spawn(f'virtctl console {vm_name} -n vm-opasnet', timeout=300)
    # child.logfile_read = sys.stdout.buffer
    
    try:
        child.sendline('')
        # Wait for login prompt - cloud-init might take a while to finish
        print(f"Waiting for login prompt on {vm_name}...")
        child.expect(['login:', f'{vm_name} login:'], timeout=300)
        
        for username, password in users_creds:
            print(f"-- Testing {username} --")
            child.sendline(username)
            child.expect('Password:', timeout=20)
            child.sendline(password)
            
            # Expect shell prompt
            i = child.expect([f'{username}@{vm_name}', '\\$', 'login:'], timeout=30)
            
            if i == 2:
                print(f"[X] Login failed for {username}")
                success = False
                continue
                
            print(f"[V] {username} login successful.")
            
            # Check IPs
            for iface, ip in expected_ips:
                print(f"Checking {iface} for IP {ip}...")
                child.sendline(f'ip -4 addr show {iface}')
                # We expect the specific IP to be in the output
                try:
                    idx = child.expect([ip, f'{username}@{vm_name}'], timeout=10)
                    if idx == 0:
                        print(f"[V] Interface {iface} has IP {ip}")
                    else:
                        # If we hit the prompt without finding the IP, check the buffer manually
                        output = child.before.decode()
                        if ip in output:
                            print(f"[V] Interface {iface} has IP {ip} (found in buffer)")
                        else:
                            print(f"[X] Interface {iface} MISSING IP {ip}")
                            print(f"DEBUG Output: {output}")
                            success = False
                except pexpect.TIMEOUT:
                     print(f"[X] Timeout checking IP {ip} on {iface}")
                     success = False
            
            child.sendline('logout')
            child.expect(['login:', f'{vm_name} login:'], timeout=20)

        child.close(force=True)
        return success
    except Exception as e:
        print(f"[!] Critical failure for {vm_name}: {e}")
        child.close(force=True)
        return False

if __name__ == "__main__":
    print("Final Verification starting...")
    
    # web-01 verification
    v1 = verify_vm('web-01', 
                   [('core', 'core'), ('suser', 'suser')], 
                   [('enp1s0', '10.215.100.101')])
    
    # web-02 verification
    v2 = verify_vm('web-02', 
                   [('core', 'core'), ('suser', 'suser')], 
                   [('enp1s0', '10.215.100.102'), ('enp2s0', '192.168.10.50')])

    if v1 and v2:
        print("\n[COMPLETE SUCCESS] Both VMs verified with correct users and IPs!")
        sys.exit(0)
    else:
        print("\n[PARTIAL FAILURE] Verification failed for one or more components.")
        sys.exit(1)
