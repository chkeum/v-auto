#!/usr/bin/env python3
import argparse
import yaml
import os
import sys
import subprocess
import getpass
import copy
import ipaddress
from jinja2 import Environment, FileSystemLoader

# Force unverified SSL for self-signed clusters
import ssl
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.path.join(BASE_DIR, 'projects')
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')

def run_command(cmd, input_data=None):
    """Executes a shell command and returns stdout."""
    try:
        result = subprocess.run(
            cmd,
            input=input_data,
            encoding='utf-8',
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        # print(f"DEBUG: Command failed: {e.stderr}")
        raise e

def load_yaml(path):
    if not os.path.exists(path):
        return {}
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def load_config(project_name, spec_name):
    """
    Loads and merges configuration:
    1. Project Config (projects/<project>/config.yaml)
    2. VM Spec (projects/<project>/specs/<spec>.yaml)
    """
    project_path = os.path.join(PROJECTS_DIR, project_name, 'config.yaml')
    spec_path = os.path.join(PROJECTS_DIR, project_name, 'specs', f"{spec_name}.yaml")
    
    if not os.path.exists(project_path):
        print(f"Error: Project config not found at {project_path}")
        sys.exit(1)
    if not os.path.exists(spec_path):
        print(f"Error: VM Spec not found at {spec_path}")
        sys.exit(1)

    proj_conf = load_yaml(project_path)
    spec_conf = load_yaml(spec_path)
    
    # Context merging
    context = {}
    context.update(proj_conf) 
    context.update(spec_conf) # Spec overrides project
    
    # Handle Environment Variables in Auth
    if 'auth' in context:
        pwd = context['auth'].get('password', '')
        if pwd.startswith('env:'):
            env_var = pwd.split(':')[1]
            context['auth']['password'] = os.environ.get(env_var, '')
            if not context['auth']['password']:
                 print(f"Warning: Environment variable {env_var} is empty.")

    return context

def render_template(template_name, context):
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    template = env.get_template(template_name)
    return template.render(context)

def get_network_config(entry, networks_catalog):
    """
    Resolves a network name from the catalog or returns the dict if it's already a dict.
    If it's a dict with a 'name' key, it merges with the catalog entry.
    """
    if isinstance(entry, dict):
        name = entry.get('name')
        if name and name in networks_catalog:
            # Merge catalog defaults with entry overrides
            conf = copy.deepcopy(networks_catalog[name])
            conf.update(entry)
            return conf
        return entry
    return networks_catalog.get(entry)

def discover_password_inputs(context):
    """
    Scans cloud_init for 'user:{{ var }}' patterns in chpasswd/list 
    to automatically identify which passwords to prompt for.
    """
    import re
    raw_ci = context.get('cloud_init', '')
    if not raw_ci: return []
    
    # regex to find 'username:{{ password_var }}'
    matches = re.findall(r'^\s*([^:\s]+):\{\{\s*(\w+)\s*\}\}', raw_ci, re.MULTILINE)
    
    discovered = []
    for user, key in matches:
        if key in ['username', 'interface_name', 'static_ip', 'gateway_ip']: continue
        
        discovered.append({
            'key': key,
            'prompt': f"Enter password for user '{user}'"
        })
    return discovered

def render_manifests(ctx):
    """Generates all K8s manifests for a VM instance."""
    manifests = []
    name = ctx['vm_name']
    
    # 1. Secret (Cloud-Init)
    # Pre-render the cloud-init configuration to substitute variables
    try:
        env = Environment()
        # Create a copy of context to avoid polluting it with rendered CI too early if needed
        # but here we want to render it.
        rendered_ci = env.from_string(ctx.get('cloud_init', '')).render(ctx)
        secret_context = ctx.copy()
        secret_context['cloud_init_content'] = rendered_ci
    except Exception as e:
        print(f"Error rendering cloud-init for {name}: {e}")
        sys.exit(1)
    secret = yaml.safe_load(render_template('secret_template.yaml', secret_context))
    manifests.append(secret)
    
    # 2. NADs
    for idx, net in enumerate(ctx['interfaces']):
        nad_name = net.get('nad_name', f"{name}-net-{idx}")
        net['name'] = f"nic{idx}" 
        net['nad_ref'] = nad_name
        
        nad_ctx = ctx.copy()
        nad_ctx.update(net)
        nad_ctx['nad_name'] = nad_name
        
        if 'ipam' in nad_ctx and not isinstance(nad_ctx['ipam'], str):
            import json
            nad_ctx['ipam'] = json.dumps(nad_ctx['ipam'])
            
        if 'bridge' in net:
             nad = yaml.safe_load(render_template('nad_template.yaml', nad_ctx))
             # We assume NADs might exist, so we apply them but handle errors downstream
             manifests.append(nad)
             
    # 3. DataVolume
    dv = yaml.safe_load(render_template('datavolume_template.yaml', ctx))
    manifests.append(dv)
    
    # 4. VM
    vm = yaml.safe_load(render_template('vm_template.yaml', ctx))
    manifests.append(vm)
    
    return manifests

def deploy_action(args):
    project = args.project
    spec = args.spec
    replicas_arg = args.replicas
    
    print(f"Loading configuration for Project: {project}, Spec: {spec}...")
    context = load_config(project, spec)
    
    # --- Interactive Inputs ---
    # 1. Discover from cloud-init (Dynamic Account Detection)
    discovered = discover_password_inputs(context)
    
    # 2. explicit inputs from config
    config_inputs = context.get('inputs', [])
    
    # 3. Merge: Prioritize discovered prompts if they match a key
    final_inputs = []
    seen_keys = set()
    
    # Map discovered for easy lookup
    discovered_map = { d['key']: d['prompt'] for d in discovered }
    
    for item in config_inputs:
        key = item['key']
        # If we discovered a specific account name for this key, use it
        if key in discovered_map:
            item['prompt'] = discovered_map[key]
        final_inputs.append(item)
        seen_keys.add(key)
        
    for d in discovered:
        if d['key'] not in seen_keys:
            final_inputs.append(d)
            seen_keys.add(d['key'])

    if not final_inputs and 'auth' in context:
         if not context['auth'].get('password'):
             final_inputs.append({'key': 'password', 'prompt': f"Password for {context['auth'].get('username', 'user')}"})

    if final_inputs:
        print("\n--- Required Inputs ---")
        for item in final_inputs:
            key = item.get('key')
            prompt_text = item.get('prompt', f"Enter value for '{key}'")
            if context.get(key): continue
            while True:
                val = getpass.getpass(f"{prompt_text}: ")
                if not val: continue
                val_confirm = getpass.getpass(f"Confirm {prompt_text}: ")
                if val != val_confirm:
                    print("Mismatch!"); continue
                context[key] = val
                break
        print("-----------------------\n")

    if 'password' in context:
        context.setdefault('auth', {})['password'] = context['password']
    
    # --- Determine Vars ---
    base_name = context.get('name_prefix', spec)
    replicas = replicas_arg if replicas_arg else context.get('replicas', 1)
    namespace = context.get('namespace', 'default')
    
    # --- Network Resolution ---
    # (Same logic as before, simpler lookup)
    proj_conf = load_yaml(os.path.join(PROJECTS_DIR, project, 'config.yaml'))
    catalog = proj_conf.get('networks', {})
    spec_networks = context.get('networks')
    final_net_list = []
    
    if isinstance(spec_networks, list):
        for net in spec_networks:
            final_net_list.append(get_network_config(net, catalog))
    elif isinstance(spec_networks, dict):
         final_net_list.append(catalog.get('default'))
    elif 'network' in context:
         final_net_list.append(get_network_config(context['network'], catalog))
    else: 
        final_net_list.append(catalog.get('default'))
        
    final_net_list = [n for n in final_net_list if n]
    if not final_net_list:
        print("Error: No valid networks resolving."); sys.exit(1)

    # --- Configuration Summary ---
    print("\n" + "="*50)
    print(f" [ Deployment Configuration Summary ] ")
    print("="*50)
    print(f" Project   : {project}")
    print(f" Spec      : {spec}")
    print(f" Namespace : {namespace}")
    print(f" Replicas  : {replicas}")
    print(f" Base Name : {base_name}")
    
    # Identify users for summary
    users = [d['prompt'].split("'")[1] for d in discovered]
    if not users:
        users = [context.get('auth', {}).get('username', 'N/A')]
    print(f" Users     : {', '.join(users)}")
    
    print(f" Image     : {context.get('image_url', 'N/A')}")
    print(f" Disk Size : {context.get('disk_size', 'N/A')}")
    print(f" StorageCls: {context.get('storage_class', 'N/A')}")
    print("-" * 50)
    print(" Network Interfaces:")
    for i, net in enumerate(final_net_list):
        net_type = net.get('type', 'multus')
        nad_name = net.get('nad_name', 'N/A')
        print(f"  NIC {i}: Type={net_type}, NAD={nad_name}")
    print("="*50 + "\n")
    
    if input("Proceed with dry-run/review? [Y/n]: ").lower() == 'n':
        print("Cancelled.")
        return

    # --- Replica Loop ---
    for i in range(replicas):
        suffix = f"-{i+1:02d}" if replicas > 1 else ""
        vm_name = f"{base_name}{suffix}"
        
        instance_ctx = context.copy()
        instance_ctx['vm_name'] = vm_name
        
        # Deep copy interfaces to modify them for this specific instance
        instance_interfaces = copy.deepcopy(final_net_list)
        
        # --- Automated Static IP Calculation ---
        # If IPAM range is present, we calculate a static IP based on replica index
        # to ensure consistency between NAD (K8s) and Cloud-Init (VM).
        for net in instance_interfaces:
            if 'ipam' in net and 'range' in net['ipam']:
                try:
                    cidr = net['ipam']['range']
                    gateway = net['ipam'].get('gateway')
                    
                    # Parse Network
                    network = ipaddress.IPv4Network(cidr, strict=False)
                    
                    # Logic: Start from .100 + index (e.g., 10.215.100.101 for replica 1)
                    # We assume the network is large enough.
                    # Verify gateway is not colliding.
                    
                    # Calculate target host offset
                    # 1-indexed loop 'i' counts 0,1. 
                    # Let's map i=0 -> .101, i=1 -> .102
                    host_offset = 101 + i 
                    
                    target_ip_obj = network.network_address + host_offset
                    target_ip = str(target_ip_obj)
                    
                    # Inject into NAD context (Switch to static IPAM for this instance)
                    # We override the type to 'static' so the NAD generated forces this IP.
                    # This replaces 'whereabouts' for this specific instance manifest.
                    net['ipam']['type'] = 'static'
                    net['ipam']['addresses'] = [{'address': f"{target_ip}/24"}] # Assuming /24, or derive from CIDR prefix len
                    # Actually better to derive prefix len
                    safe_cidr_suffix = str(network.prefixlen)
                    net['ipam']['addresses'] = [{'address': f"{target_ip}/{safe_cidr_suffix}"}]
                    # if gateway:
                    #     net['ipam']['gateway'] = gateway # Commented out as per instruction
                    # Only add specific routes if needed, avoid default route on secondary NIC
                    # net['ipam']['routes'] = [{"dst": "0.0.0.0/0", "gw": gateway}]
                    pass
                    
                    # Update NAD name to be instance-specific to avoid conflicts with static IP
                    orig_nad = net.get('nad_name', 'net')
                    net['nad_name'] = f"{vm_name}-{orig_nad}"
                    
                    # Inject variables for Cloud-Init (Jinja2)
                    instance_ctx['static_ip'] = f"{target_ip}/{safe_cidr_suffix}"
                    instance_ctx['gateway_ip'] = gateway
                    instance_ctx['interface_name'] = 'enp2s0' # Default assumption for 2nd NIC, can make configurable
                    
                    print(f"    [Auto-Net] Calculated Static IP: {target_ip} (GW: {gateway}, NAD: {net['nad_name']})")
                    
                except Exception as e:
                    print(f"    [Warning] Failed to calculate static IP: {e}")

        instance_ctx['interfaces'] = instance_interfaces
        
        print(f"\n>>> Preparing Replica {i+1}/{replicas}: {vm_name}")
        manifests = render_manifests(instance_ctx)
        
        # Dry Run Output
        print(f"\n[ Dry-Run: {vm_name} Manifests ]")
        for m in manifests:
            kind = m.get('kind', 'Unknown')
            m_name = m.get('metadata', {}).get('name', 'Unknown')
            print(f"\n--- Resource: {kind} / {m_name} ---")
            print(yaml.dump(m))
            
        # Confirm
        ans = input(f"\nCreate resources for {vm_name}? [y/N/q(uit)]: ").lower()
        if ans == 'q': return
        if ans != 'y': 
            print(f"Skipping {vm_name}."); continue
            
        # Apply
        print(f"Applying resources for {vm_name}...")
        for m in manifests:
            ignore = (m['kind'] == 'NetworkAttachmentDefinition')
            apply_k8s_resource(m, namespace, ignore_exists=ignore)
        print(f"--> {vm_name} Deployed.")

def apply_k8s_resource(manifest, namespace, ignore_exists=False):
    kind = manifest['kind']
    name = manifest['metadata']['name']
    
    cmd = ['oc', 'apply', '-f', '-', '-n', namespace]
    input_str = yaml.dump(manifest)
    
    try:
        run_command(cmd, input_data=input_str)
        print(f"[OK] Applied {kind}: {name}")
    except Exception as e:
        if ignore_exists:
            # Simple check or just pass
            pass
        else:
            print(f"[FAIL] {kind} {name}: {e}")

def delete_action(args):
    project = args.project
    spec = args.spec
    target = args.target # Optional specific name
    
    context = load_config(project, spec)
    namespace = context.get('namespace', 'default')
    base_name = context.get('name_prefix', spec)
    
    # Identify what to delete
    # If target is set, delete one.
    # If not, delete ALL replicas roughly? Or Pattern?
    # Safer to ask matching pattern.
    
    selector = target if target else base_name
    print(f"Deleting resources matching '{selector}' in '{namespace}'...")
    
    # Interactive check
    if input("Are you sure? [y/N]: ").lower() != 'y':
        print("Cancelled.")
        return

    # Delete commands (VM, DV, Secret)
    # Using 'oc delete ... -l ...' is best if we had labels.
    # Creating 'vm_manager' label in config was a good idea.
    # Let's assume common_labels 'managed-by: vm-manager' is applied.
    # And maybe 'vm-role: spec-name'
    
    # For now, simplistic approach: match names.
    objs = ['vm', 'dv', 'secret', 'net-attach-def']
    
    if target:
        # Delete specific
        for kind in objs:
             run_command(['oc', 'delete', kind, target, '-n', namespace, '--ignore-not-found'])
             run_command(['oc', 'delete', kind, f"{target}-root-disk", '-n', namespace, '--ignore-not-found'])
             run_command(['oc', 'delete', kind, f"{target}-cloud-init", '-n', namespace, '--ignore-not-found'])
             # Check for any NIC NADs (assuming name prefix)
             # This is a bit brute force but matches our naming scheme
             for i in range(4): # Check up to 4 interfaces
                 run_command(['oc', 'delete', kind, f"{target}-net-{i}", '-n', namespace, '--ignore-not-found'])
                 # Also check the new naming scheme: {target}-{orig_nad}
                 # Since we don't know orig_nad here, we might need a regex or label
                 # But oc delete -l is better.
    else:
        # Delete all loop? Or label?
        # Trying to guess names is risky.
        # But for 'replicas', names are predictable.
        replicas = args.replicas if args.replicas else int(context.get('replicas', 1))
        for i in range(replicas):
            suffix = f"-{i+1:02d}" if replicas > 1 else ""
            name = f"{base_name}{suffix}"
            print(f"Removing {name}...")
            run_command(['oc', 'delete', 'vm', name, '-n', namespace, '--ignore-not-found'])
            run_command(['oc', 'delete', 'dv', f"{name}-root-disk", '-n', namespace, '--ignore-not-found'])
            run_command(['oc', 'delete', 'secret', f"{name}-cloud-init", '-n', namespace, '--ignore-not-found'])
            # Cleanup NADs matching our naming scheme
            run_command(['oc', 'delete', 'net-attach-def', f"{name}-br-virt-net", '-n', namespace, '--ignore-not-found'])

def list_action(args):
    context = load_config(args.project, args.spec) 
    # Actually 'list' probably shouldn't require 'spec'?
    # It might just list all in project.
    # But current arg parser expects spec? I'll make spec optional in parser if possible.
    ns = context.get('namespace', 'default')
    
    print(f"Listing VMs in {ns}...")
    # Table output
    cmd = ['oc', 'get', 'vm', '-n', ns, '-o', 'wide']
    print(run_command(cmd))

def status_action(args):
    # Similar to list but maybe more detail
    list_action(args)


def main():
    parser = argparse.ArgumentParser(description="Multi-Project VM Manager")
    
    # 1. Collect all positional arguments in one list
    parser.add_argument('args_pos', nargs='*', metavar='project spec action', 
                        help="Positional arguments: project, spec, and action")
    
    # 2. Define optional flags
    parser.add_argument('--vendor', '--project', dest='project_flag', help="Project name")
    parser.add_argument('--spec', dest='spec_flag', help="VM Spec name")
    parser.add_argument('--action', dest='action_flag', 
                        choices=['deploy', 'delete', 'list', 'status'], help="Action to perform")
    
    parser.add_argument('--replicas', type=int, help="Override replica count")
    parser.add_argument('--target', help="Specific target name for delete")
    
    args = parser.parse_args()
    
    # 3. Intelligent Resolution Logic:
    # Flags take higher priority. Remaining positional arguments fill empty gaps.
    project = args.project_flag
    spec = args.spec_flag
    action = args.action_flag
    
    for p in args.args_pos:
        if not project:
            project = p
        elif not spec:
            spec = p
        elif not action and p in ['deploy', 'delete', 'list', 'status']:
            action = p
        elif not action: # If it's not a known choice but action is still empty
            action = p

    if not project or not spec or not action or action not in ['deploy', 'delete', 'list', 'status']:
        parser.print_help()
        print("\nError: project, spec, and action are all required.")
        print("Example: python3 vm_manager.py samsung web deploy")
        print("Example: python3 vm_manager.py --vendor samsung --spec web delete")
        sys.exit(1)
        
    args.project = project
    args.spec = spec
    args.action = action
    
    if args.action == 'deploy':
        deploy_action(args)
    elif args.action == 'delete':
        delete_action(args)
    elif args.action in ['list', 'status']:
        list_action(args)

if __name__ == '__main__':
    main()
