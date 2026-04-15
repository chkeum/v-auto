# Test Coverage Analysis: v-auto

## Executive Summary

The v-auto codebase currently has **zero automated tests**. This analysis identifies critical areas requiring test coverage and proposes a comprehensive testing strategy.

| Metric | Current | Target |
|--------|---------|--------|
| Test Files | 0 | 8+ |
| Unit Tests | 0 | 50+ |
| Integration Tests | 0 | 10+ |
| Code Coverage | 0% | 80%+ |

---

## Current State Assessment

### Architecture Overview

The application is a single monolithic file (`vm_manager.py`, 1,210 lines) containing:

- **17 functions** with no test coverage
- **Complex regex patterns** for password discovery
- **External dependencies** (`oc` CLI, Jinja2 templates)
- **Configuration merging logic** with multiple priority levels
- **IP address validation and CIDR calculations**

### Risk Analysis

| Component | Risk Level | Impact of Bugs |
|-----------|------------|----------------|
| Password Discovery (`discover_password_inputs`) | **HIGH** | Security - missed passwords, auth failures |
| Network/IP Validation | **HIGH** | VM unreachable, network misconfiguration |
| Configuration Merging | **HIGH** | Unexpected defaults, deployment failures |
| Template Rendering | **MEDIUM** | Malformed K8s resources, deployment failures |
| CLI Argument Parsing | **MEDIUM** | User confusion, incorrect actions |
| Status Reporting | **LOW** | Display issues, no functional impact |

---

## Priority 1: Critical Functions (High Risk)

### 1.1 Password Discovery (`discover_password_inputs`)

**Location:** `vm_manager.py:206-254`

**Why Critical:** This function uses complex regex to extract password variables from cloud-init templates. Bugs here could:
- Miss users requiring passwords (deployment fails)
- Extract wrong variable names (passwords not prompted)
- Create security vulnerabilities

**Current Implementation Concerns:**
```python
# Pattern 1: chpasswd style - 'username:{{ var }}'
chpasswd_matches = re.findall(r'^\s*([^:\s\-]+):\{\{\s*([\w]+)(?:\|[^}]+)?\s*\}\}', raw_ci, re.MULTILINE)

# Pattern 2: users list style with passwd field
pass_match = re.search(r'^\s*pass(?:wd|word):\s*[\'"]?\{\{\s*(\w+).*?\}\}[\'"]?', block, re.MULTILINE)
```

**Proposed Test Cases:**

```python
# tests/test_password_discovery.py

class TestPasswordDiscovery:

    def test_chpasswd_single_user(self):
        """Test basic chpasswd format: 'root:{{ root_password }}'"""
        context = {'cloud_init': '''
chpasswd:
  list:
    root:{{ root_password }}
'''}
        result = discover_password_inputs(context)
        assert len(result) == 1
        assert result[0]['key'] == 'root_password'
        assert 'root' in result[0]['prompt']

    def test_chpasswd_multiple_users(self):
        """Test multiple users in chpasswd format"""
        context = {'cloud_init': '''
chpasswd:
  list:
    root:{{ root_password }}
    admin:{{ admin_password }}
'''}
        result = discover_password_inputs(context)
        assert len(result) == 2
        keys = {r['key'] for r in result}
        assert keys == {'root_password', 'admin_password'}

    def test_users_list_with_passwd(self):
        """Test cloud-init users list format"""
        context = {'cloud_init': '''
users:
  - name: devops
    passwd: {{ devops_password | hash_password }}
'''}
        result = discover_password_inputs(context)
        assert len(result) == 1
        assert result[0]['key'] == 'devops_password'

    def test_users_list_with_password_keyword(self):
        """Test 'password' keyword (alternative to 'passwd')"""
        context = {'cloud_init': '''
users:
  - name: admin
    password: "{{ admin_pass }}"
'''}
        result = discover_password_inputs(context)
        assert len(result) == 1
        assert result[0]['key'] == 'admin_pass'

    def test_mixed_formats(self):
        """Test combination of chpasswd and users list"""
        context = {'cloud_init': '''
chpasswd:
  list:
    root:{{ root_password }}
users:
  - name: developer
    passwd: {{ dev_password | hash_password }}
'''}
        result = discover_password_inputs(context)
        assert len(result) == 2

    def test_ignore_non_password_variables(self):
        """Ensure system variables are not treated as passwords"""
        context = {'cloud_init': '''
users:
  - name: {{ username }}
    passwd: {{ user_password }}
network:
  interface_name: {{ interface_name }}
'''}
        result = discover_password_inputs(context)
        # Should only find user_password, not username or interface_name
        assert len(result) == 1
        assert result[0]['key'] == 'user_password'

    def test_empty_cloud_init(self):
        """Handle missing or empty cloud_init gracefully"""
        assert discover_password_inputs({}) == []
        assert discover_password_inputs({'cloud_init': ''}) == []
        assert discover_password_inputs({'cloud_init': None}) == []

    def test_no_duplicates(self):
        """Same password variable referenced multiple times"""
        context = {'cloud_init': '''
chpasswd:
  list:
    root:{{ shared_password }}
    admin:{{ shared_password }}
'''}
        result = discover_password_inputs(context)
        # Should only prompt once
        assert len(result) == 1
        assert result[0]['key'] == 'shared_password'
```

---

### 1.2 Network Configuration Resolution (`get_network_config`)

**Location:** `vm_manager.py:183-204`

**Why Critical:** This function resolves network names from the infrastructure catalog. Bugs could cause:
- Network attachment failures
- Wrong bridge assignments
- Missing IPAM configuration

**Proposed Test Cases:**

```python
# tests/test_network_config.py

class TestGetNetworkConfig:

    @pytest.fixture
    def sample_catalog(self):
        return {
            'pod': {'type': 'pod'},
            'svc-net': {
                'type': 'multus',
                'bridge': 'br-svc',
                'nad_name': 'svc-nad',
                'ipam': {'type': 'dhcp'}
            },
            'mgmt': {
                'type': 'multus',
                'bridge': 'br-mgmt',
                'ipam': {'type': 'static', 'range': '10.0.0.0/24'}
            }
        }

    def test_string_reference_resolution(self, sample_catalog):
        """Resolve network by string name"""
        result = get_network_config('svc-net', sample_catalog)
        assert result['bridge'] == 'br-svc'
        assert result['name'] == 'svc-net'

    def test_dict_with_name_merges_catalog(self, sample_catalog):
        """Dict entry with 'name' key should merge with catalog"""
        entry = {'name': 'svc-net', 'mtu': 9000}
        result = get_network_config(entry, sample_catalog)
        assert result['bridge'] == 'br-svc'  # From catalog
        assert result['mtu'] == 9000  # From override
        assert result['name'] == 'svc-net'

    def test_dict_override_precedence(self, sample_catalog):
        """Override values should take precedence over catalog"""
        entry = {'name': 'svc-net', 'bridge': 'br-custom'}
        result = get_network_config(entry, sample_catalog)
        assert result['bridge'] == 'br-custom'  # Override wins

    def test_inline_dict_no_catalog_match(self, sample_catalog):
        """Dict without matching catalog entry returned as-is"""
        entry = {'bridge': 'br-new', 'type': 'multus'}
        result = get_network_config(entry, sample_catalog)
        assert result == entry

    def test_unknown_string_returns_none(self, sample_catalog):
        """Unknown network name should return None"""
        result = get_network_config('nonexistent', sample_catalog)
        assert result is None

    def test_catalog_entry_is_copied(self, sample_catalog):
        """Ensure original catalog is not mutated"""
        original_bridge = sample_catalog['svc-net']['bridge']
        entry = {'name': 'svc-net', 'bridge': 'modified'}
        get_network_config(entry, sample_catalog)
        assert sample_catalog['svc-net']['bridge'] == original_bridge
```

---

### 1.3 Configuration Loading (`load_config`)

**Location:** `vm_manager.py:101-170`

**Why Critical:** This function handles configuration merging with multiple priority levels. Bugs could cause:
- Wrong default values applied
- Instance-specific overrides ignored
- Environment variable interpolation failures

**Proposed Test Cases:**

```python
# tests/test_config_loading.py

class TestLoadConfig:

    @pytest.fixture
    def mock_spec_file(self, tmp_path, monkeypatch):
        """Create temporary spec files for testing"""
        project_dir = tmp_path / "projects" / "test-project"
        project_dir.mkdir(parents=True)
        monkeypatch.setattr('vm_manager.PROJECTS_DIR', str(tmp_path / "projects"))
        return project_dir

    def test_default_values_applied(self, mock_spec_file):
        """Convention defaults should be applied"""
        spec = mock_spec_file / "web.yaml"
        spec.write_text("name_prefix: web\n")

        context = load_config('test-project', 'web')

        assert context['namespace'] == 'vm-test-project'  # Convention
        assert context['cpu'] == 2  # Default
        assert context['memory'] == '4Gi'  # Default
        assert context['disk_size'] == '20Gi'  # Default

    def test_spec_overrides_defaults(self, mock_spec_file):
        """Spec values should override defaults"""
        spec = mock_spec_file / "web.yaml"
        spec.write_text("""
cpu: 4
memory: 8Gi
namespace: custom-ns
""")
        context = load_config('test-project', 'web')

        assert context['cpu'] == 4
        assert context['memory'] == '8Gi'
        assert context['namespace'] == 'custom-ns'

    def test_common_block_structure(self, mock_spec_file):
        """Support 'common' block with instances"""
        spec = mock_spec_file / "web.yaml"
        spec.write_text("""
common:
  cpu: 2
  memory: 4Gi
instances:
  - name: web-01
  - name: web-02
""")
        context = load_config('test-project', 'web')

        assert len(context['instances']) == 2
        assert context['cpu'] == 2

    def test_env_variable_in_auth(self, mock_spec_file, monkeypatch):
        """Environment variable interpolation in auth.password"""
        monkeypatch.setenv('VM_PASSWORD', 'secret123')
        spec = mock_spec_file / "web.yaml"
        spec.write_text("""
auth:
  password: env:VM_PASSWORD
""")
        context = load_config('test-project', 'web')

        assert context['auth']['password'] == 'secret123'

    def test_legacy_specs_directory(self, mock_spec_file):
        """Support legacy specs/ subdirectory structure"""
        specs_dir = mock_spec_file / "specs"
        specs_dir.mkdir()
        spec = specs_dir / "legacy.yaml"
        spec.write_text("cpu: 1\n")

        context = load_config('test-project', 'legacy')
        assert context['cpu'] == 1

    def test_flat_layout_precedence(self, mock_spec_file):
        """Flat layout should take precedence over specs/ directory"""
        # Create both flat and legacy
        flat_spec = mock_spec_file / "web.yaml"
        flat_spec.write_text("cpu: 4\n")

        specs_dir = mock_spec_file / "specs"
        specs_dir.mkdir()
        legacy_spec = specs_dir / "web.yaml"
        legacy_spec.write_text("cpu: 2\n")

        context = load_config('test-project', 'web')
        assert context['cpu'] == 4  # Flat takes precedence

    def test_storage_class_mapping(self, mock_spec_file):
        """Storage configuration should be properly flattened"""
        spec = mock_spec_file / "web.yaml"
        spec.write_text("""
storage:
  class: fast-ssd
  access_modes:
    - ReadWriteMany
""")
        context = load_config('test-project', 'web')

        assert context['storage_class'] == 'fast-ssd'
        assert context['access_mode'] == 'ReadWriteMany'
```

---

### 1.4 IP Address Validation (in `deploy_action`)

**Location:** `vm_manager.py:609-627`

**Why Critical:** IP validation ensures VMs get correct network configuration. Bugs could:
- Allow invalid IPs that break networking
- Miscalculate CIDR prefixes
- Fail to detect out-of-range IPs

**Proposed Test Cases:**

```python
# tests/test_ip_validation.py

import ipaddress

class TestIPValidation:
    """Test IP validation logic used in deploy_action"""

    def test_valid_ip_in_subnet(self):
        """IP within subnet range should be valid"""
        subnet_cidr = '10.0.0.0/24'
        target_ip = '10.0.0.50'

        network = ipaddress.IPv4Network(subnet_cidr, strict=False)
        assert ipaddress.IPv4Address(target_ip) in network

    def test_ip_outside_subnet(self):
        """IP outside subnet should be detected"""
        subnet_cidr = '10.0.0.0/24'
        target_ip = '10.0.1.50'  # Wrong subnet

        network = ipaddress.IPv4Network(subnet_cidr, strict=False)
        assert ipaddress.IPv4Address(target_ip) not in network

    def test_cidr_prefix_calculation(self):
        """Correct CIDR prefix should be extracted"""
        subnet_cidr = '192.168.1.0/24'
        network = ipaddress.IPv4Network(subnet_cidr, strict=False)
        assert network.prefixlen == 24

    def test_various_subnet_sizes(self):
        """Test different subnet sizes"""
        test_cases = [
            ('10.0.0.0/8', '10.255.255.254', True),
            ('10.0.0.0/8', '11.0.0.1', False),
            ('172.16.0.0/16', '172.16.255.1', True),
            ('192.168.1.0/24', '192.168.1.254', True),
            ('192.168.1.0/28', '192.168.1.20', False),  # Out of /28 range
        ]
        for subnet, ip, expected in test_cases:
            network = ipaddress.IPv4Network(subnet, strict=False)
            result = ipaddress.IPv4Address(ip) in network
            assert result == expected, f"{ip} in {subnet} should be {expected}"

    def test_invalid_ip_format(self):
        """Invalid IP format should raise exception"""
        with pytest.raises(ipaddress.AddressValueError):
            ipaddress.IPv4Address('invalid')

    def test_invalid_cidr_format(self):
        """Invalid CIDR should raise exception"""
        with pytest.raises(ValueError):
            ipaddress.IPv4Network('10.0.0.0/33')  # Invalid prefix
```

---

## Priority 2: Important Functions (Medium Risk)

### 2.1 Template Rendering (`render_template`, `render_manifests`)

**Location:** `vm_manager.py:172-181, 256-349`

**Why Important:** Generates Kubernetes resources. Bugs create invalid YAML that fails deployment.

**Proposed Test Cases:**

```python
# tests/test_template_rendering.py

class TestRenderTemplate:

    def test_basic_variable_substitution(self, tmp_path):
        """Variables should be correctly substituted"""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "test.yaml").write_text("name: {{ vm_name }}")

        # Temporarily override TEMPLATES_DIR
        context = {'vm_name': 'test-vm'}
        result = render_template('test.yaml', context)
        assert 'name: test-vm' in result

    def test_to_json_filter(self):
        """to_json filter should serialize objects"""
        env = Environment()
        env.filters['to_json'] = lambda v: json.dumps(v)

        template = env.from_string("{{ data | to_json }}")
        result = template.render(data={'key': 'value'})
        assert result == '{"key": "value"}'

    def test_to_yaml_filter(self):
        """to_yaml filter should serialize to YAML block format"""
        # Test the filter function directly
        def to_yaml_filter(val):
            return yaml.dump(val, default_flow_style=False, sort_keys=False).strip()

        result = to_yaml_filter({'ethernets': {'eth0': {'addresses': ['10.0.0.1/24']}}})
        assert 'ethernets:' in result
        assert 'eth0:' in result

    def test_hash_password_filter(self):
        """hash_password filter should create SHA512 hash"""
        import crypt

        def hash_password_filter(pwd):
            if not pwd: return ""
            return crypt.crypt(pwd, crypt.mksalt(crypt.METHOD_SHA512))

        result = hash_password_filter('testpass')
        assert result.startswith('$6$')  # SHA512 prefix
        assert len(result) > 50

    def test_hash_password_empty_input(self):
        """Empty password should return empty string"""
        def hash_password_filter(pwd):
            if not pwd: return ""
            return crypt.crypt(pwd, crypt.mksalt(crypt.METHOD_SHA512))

        assert hash_password_filter('') == ''
        assert hash_password_filter(None) == ''


class TestRenderManifests:

    def test_manifest_types_generated(self):
        """Should generate Secret, NAD, DataVolume, VM manifests"""
        ctx = {
            'vm_name': 'test-vm',
            'project_name': 'proj',
            'spec_name': 'spec',
            'namespace': 'test-ns',
            'cloud_init': '',
            'interfaces': [{'bridge': 'br0', 'type': 'multus'}],
            'image_url': 'http://example.com/image.qcow2',
            'disk_size': '20Gi',
            'cpu': 2,
            'memory': '4Gi'
        }

        manifests = render_manifests(ctx)
        kinds = [m['kind'] for m in manifests]

        assert 'Secret' in kinds
        assert 'DataVolume' in kinds
        assert 'VirtualMachine' in kinds

    def test_labels_applied_to_all_manifests(self):
        """v-auto labels should be on all resources"""
        ctx = {
            'vm_name': 'test-vm',
            'project_name': 'myproj',
            'spec_name': 'myspec',
            # ... other required context
        }

        manifests = render_manifests(ctx)

        for m in manifests:
            labels = m.get('metadata', {}).get('labels', {})
            assert labels.get('v-auto/managed') == 'true'
            assert labels.get('v-auto/project') == 'myproj'
            assert labels.get('v-auto/spec') == 'myspec'
```

---

### 2.2 CLI Argument Parsing (`main`)

**Location:** `vm_manager.py:1095-1210`

**Why Important:** Users interact through CLI. Bad parsing causes confusion and errors.

**Proposed Test Cases:**

```python
# tests/test_cli_parsing.py

class TestCLIParsing:

    def test_positional_args_parsed(self):
        """Basic positional: project spec action"""
        sys.argv = ['vman', 'opasnet', 'web', 'deploy']
        # Would need to capture args after parsing
        # Test that project='opasnet', spec='web', action='deploy'

    def test_flag_based_args(self):
        """Flag-based: --project --spec --action"""
        sys.argv = ['vman', '--project', 'opasnet', '--spec', 'web', '--action', 'deploy']
        # Test flag parsing

    def test_slash_syntax(self):
        """Support project/spec shorthand"""
        sys.argv = ['vman', 'opasnet/web', 'deploy']
        # Should parse as project='opasnet', spec='web'

    def test_action_detection_in_any_position(self):
        """Action keyword should be detected anywhere"""
        sys.argv = ['vman', 'deploy', 'opasnet', 'web']
        # action='deploy' should be detected

    def test_missing_required_args_error(self):
        """Missing arguments should produce helpful error"""
        sys.argv = ['vman', 'opasnet']  # Missing spec and action
        # Should exit with error listing missing: spec, action

    def test_target_flag_with_action(self):
        """--target flag should work with actions"""
        sys.argv = ['vman', 'opasnet', 'web', 'delete', '--target', 'web-01']
        # target='web-01' should be captured

    def test_dry_run_flag(self):
        """--dry-run should be recognized"""
        sys.argv = ['vman', 'opasnet', 'web', 'deploy', '--dry-run']
        # dry_run=True

    def test_yes_flag_short_and_long(self):
        """Both -y and --yes should work"""
        sys.argv = ['vman', 'opasnet', 'web', 'deploy', '-y']
        # yes=True
```

---

### 2.3 Infrastructure Loading (`load_infrastructure_config`)

**Location:** `vm_manager.py:63-99`

**Why Important:** Loads network/image catalogs. Priority merging bugs cause wrong infrastructure.

**Proposed Test Cases:**

```python
# tests/test_infrastructure_loading.py

class TestLoadInfrastructureConfig:

    def test_spec_level_overrides_project_level(self, mock_project):
        """Spec-defined infrastructure should override project files"""
        # Create project-level networks.yaml with network 'prod'
        # Create spec context with different 'prod' definition
        # Spec version should win

    def test_merge_networks_images_storage(self, mock_project):
        """All three infrastructure types should be merged"""
        spec_context = {
            'infrastructure': {
                'networks': {'new-net': {'bridge': 'br-new'}},
                'images': {'ubuntu': {'url': 'http://new'}},
                'storage_profiles': {'fast': {'class': 'nvme'}}
            }
        }
        result = load_infrastructure_config('test', spec_context)

        assert 'new-net' in result['networks']
        assert 'ubuntu' in result['images']
        assert 'fast' in result['storage_profiles']

    def test_empty_project_directory(self):
        """Handle missing infrastructure directory gracefully"""
        result = load_infrastructure_config('nonexistent-project', None)

        assert result['networks'] == {}
        assert result['images'] == {}
        assert result['storage_profiles'] == {}
```

---

## Priority 3: Supporting Functions (Lower Risk)

### 3.1 Command Execution (`run_command`)

**Location:** `vm_manager.py:27-42`

**Test Strategy:** Mock subprocess for unit tests, integration tests with real commands.

```python
# tests/test_command_execution.py

class TestRunCommand:

    def test_successful_command(self):
        """Successful command returns stdout"""
        result = run_command(['echo', 'hello'])
        assert result == 'hello'

    def test_failed_command_raises(self):
        """Failed command raises exception with stderr"""
        with pytest.raises(Exception) as exc:
            run_command(['false'])  # Always fails
        # Check error message

    def test_input_data_passed(self):
        """Input data should be passed to stdin"""
        result = run_command(['cat'], input_data='test input')
        assert result == 'test input'
```

### 3.2 YAML Loading (`load_yaml`)

**Location:** `vm_manager.py:57-61`

```python
# tests/test_yaml_loading.py

class TestLoadYaml:

    def test_valid_yaml_file(self, tmp_path):
        """Load valid YAML file"""
        f = tmp_path / "test.yaml"
        f.write_text("key: value\nlist:\n  - item1")

        result = load_yaml(str(f))
        assert result['key'] == 'value'
        assert result['list'] == ['item1']

    def test_nonexistent_file_returns_empty(self):
        """Missing file should return empty dict"""
        result = load_yaml('/nonexistent/path.yaml')
        assert result == {}

    def test_empty_file_returns_none(self, tmp_path):
        """Empty YAML file returns None (yaml.safe_load behavior)"""
        f = tmp_path / "empty.yaml"
        f.write_text("")
        result = load_yaml(str(f))
        assert result is None  # Or handle this case
```

### 3.3 Table Formatting (`clean_print_table`)

**Location:** `vm_manager.py:805-814`

```python
# tests/test_output_formatting.py

class TestCleanPrintTable:

    def test_replaces_none_values(self, capsys):
        """<none> should be replaced with dashes"""
        output = "NAME    STATUS\ntest    <none>"
        clean_print_table(output, "Test")
        captured = capsys.readouterr()
        assert "  -   " in captured.out
        assert "<none>" not in captured.out

    def test_empty_output_message(self, capsys):
        """Empty output shows 'no X found' message"""
        clean_print_table("", "Resources")
        captured = capsys.readouterr()
        assert "No resources found" in captured.out.lower()
```

---

## Recommended Testing Framework Setup

### Install Dependencies

```bash
pip install pytest pytest-cov pytest-mock pyyaml
```

### Project Structure

```
v-auto/
├── vm_manager.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Shared fixtures
│   ├── test_password_discovery.py
│   ├── test_network_config.py
│   ├── test_config_loading.py
│   ├── test_ip_validation.py
│   ├── test_template_rendering.py
│   ├── test_cli_parsing.py
│   ├── test_infrastructure_loading.py
│   └── test_integration.py      # End-to-end tests
├── pytest.ini
└── requirements-dev.txt
```

### pytest.ini Configuration

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_functions = test_*
addopts = -v --tb=short --strict-markers
markers =
    unit: Unit tests (no external dependencies)
    integration: Integration tests (may require oc CLI)
    slow: Slow-running tests
```

### conftest.py (Shared Fixtures)

```python
# tests/conftest.py
import pytest
import tempfile
import os

@pytest.fixture
def mock_projects_dir(tmp_path, monkeypatch):
    """Create temporary projects directory"""
    projects = tmp_path / "projects"
    projects.mkdir()
    monkeypatch.setattr('vm_manager.PROJECTS_DIR', str(projects))
    return projects

@pytest.fixture
def sample_context():
    """Standard VM context for testing"""
    return {
        'vm_name': 'test-vm',
        'namespace': 'test-ns',
        'project_name': 'test-project',
        'spec_name': 'test-spec',
        'cpu': 2,
        'memory': '4Gi',
        'disk_size': '20Gi',
        'image_url': 'http://example.com/image.qcow2',
        'cloud_init': '',
        'interfaces': []
    }

@pytest.fixture
def mock_oc_command(monkeypatch):
    """Mock oc CLI commands"""
    def mock_run(cmd, input_data=None):
        if 'get' in cmd:
            return "NAME    STATUS\ntest    Running"
        return ""
    monkeypatch.setattr('vm_manager.run_command', mock_run)
```

---

## Refactoring Recommendations for Testability

The current monolithic structure makes testing difficult. Consider these refactoring steps:

### 1. Extract Pure Functions

Move stateless logic into separate modules:

```
v-auto/
├── lib/
│   ├── __init__.py
│   ├── config.py          # load_config, load_yaml, load_infrastructure_config
│   ├── network.py         # get_network_config, IP validation
│   ├── templates.py       # render_template, render_manifests
│   ├── discovery.py       # discover_password_inputs
│   └── cli.py             # Argument parsing
├── vm_manager.py          # Main orchestration only
```

### 2. Dependency Injection for External Commands

```python
# Instead of:
def ensure_namespace(namespace):
    run_command(['oc', 'get', 'namespace', namespace])

# Use:
def ensure_namespace(namespace, runner=run_command):
    runner(['oc', 'get', 'namespace', namespace])
```

### 3. Separate I/O from Logic

```python
# Current: Mixed I/O and logic
def deploy_action(args):
    print("Loading...")  # I/O
    context = load_config(...)  # Logic
    print("Deploying...")  # I/O

# Better: Return results, let caller handle I/O
def prepare_deployment(project, spec):
    context = load_config(project, spec)
    manifests = render_manifests(context)
    return DeploymentPlan(context, manifests)
```

---

## Implementation Roadmap

### Phase 1: Foundation (Week 1)
- [ ] Set up pytest infrastructure
- [ ] Create `conftest.py` with shared fixtures
- [ ] Write tests for `discover_password_inputs` (highest risk)
- [ ] Write tests for `get_network_config`

### Phase 2: Core Logic (Week 2)
- [ ] Write tests for `load_config`
- [ ] Write tests for `load_infrastructure_config`
- [ ] Write tests for IP validation logic
- [ ] Write tests for template rendering

### Phase 3: CLI & Integration (Week 3)
- [ ] Write tests for CLI argument parsing
- [ ] Create mock fixtures for `oc` commands
- [ ] Write integration tests for full deployment flow
- [ ] Add CI/CD pipeline with test automation

### Phase 4: Coverage Goals (Week 4)
- [ ] Achieve 80% code coverage
- [ ] Add edge case tests based on coverage gaps
- [ ] Document testing patterns for contributors

---

## Summary

| Priority | Component | Test Count | Risk Mitigated |
|----------|-----------|------------|----------------|
| P1 | Password Discovery | 8+ | Security, Auth failures |
| P1 | Network Config | 6+ | Network misconfiguration |
| P1 | Config Loading | 7+ | Deployment failures |
| P1 | IP Validation | 6+ | Invalid networking |
| P2 | Template Rendering | 6+ | Malformed K8s resources |
| P2 | CLI Parsing | 8+ | User experience |
| P2 | Infrastructure Loading | 3+ | Wrong infrastructure |
| P3 | Command Execution | 3+ | Error handling |
| P3 | YAML Loading | 3+ | File handling |
| P3 | Output Formatting | 2+ | Display issues |

**Total Estimated Tests:** 50+ unit tests, 10+ integration tests

This analysis provides a roadmap to transform v-auto from a completely untested codebase to one with comprehensive test coverage, significantly reducing the risk of bugs in production deployments.
