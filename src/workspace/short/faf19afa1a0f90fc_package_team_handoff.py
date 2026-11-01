"""Copy the current board release and its matching FPGA sources; never deploy."""

import argparse
import base64
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import stat
import xml.etree.ElementTree as ET
import zipfile

from run_soak_stage import ROOT, PROD, connect, command
from deploy_ssvep_rail_coalesce import sudo


FPGA = Path('D:/ican/ican_fpga_project/GuardianLoop_Z15_2025_1')
PROJECT_NAME = 'GuardianLoop_Z15_2025_1'
EXPECTED_BIT = 'c39b891704471a712fb7be3591841af1dd6791387957b873b11450c99eca41ca'
EXPECTED_HWH = '2ab7ffa36398be4eee20d90512c7f1c6d29a7066c9d1bf0683a3bcad2501f92b'
UNITS = ('guardianloop-startup.service', 'guardianloop-cyton.service',
         'guardianloop-web.service', 'guardianloop-ap.service', 'guardianloop-dhcp.service')
SKIP_DIRS = {'.git', '.Xil', '__pycache__', '.pytest_cache', '.sim_project', '.synth_project', 'toolchain'}
DEV_SUFFIXES = {'.py', '.ps1', '.tcl', '.v', '.sv', '.vhd', '.h', '.c', '.sh', '.md',
                '.json', '.xdc', '.xml', '.mem', '.hex', '.conf', '.service', '.js', '.cjs'}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Bundle:
    def __init__(self, root):
        self.root = root
        self.files = []
        self.client = None

    def local(self, source, relative):
        target = self.root / relative
        if target.exists():
            raise FileExistsError(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        digest = sha(source)
        if sha(target) != digest:
            raise RuntimeError('Copy checksum mismatch: ' + str(source))
        self.files.append({'path': relative.as_posix(), 'source': str(source),
                           'sha256': digest, 'bytes': target.stat().st_size})

    def tree(self, source, relative, suffixes=None, generated_bd_ip=False):
        for item in sorted(source.rglob('*')):
            part = item.relative_to(source)
            if any(name in SKIP_DIRS for name in part.parts) or not item.is_file():
                continue
            if generated_bd_ip and 'bd' in part.parts and 'ip' in part.parts:
                continue
            if suffixes is not None and item.suffix.lower() not in suffixes and item.name != 'Makefile':
                continue
            self.local(item, relative / part)

    def remote(self, sftp, source, relative):
        target = self.root / relative
        if target.exists():
            raise FileExistsError(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        before = sftp.stat(source)
        try:
            sftp.get(source, str(target))
            with sftp.open(source, 'rb') as stream:
                remote_hash = hashlib.sha256(stream.read()).hexdigest()
        except PermissionError:
            data = base64.b64decode(sudo(self.client, 'base64 -w 0 ' + shlex.quote(source)), validate=True)
            target.write_bytes(data)
            remote_hash = sudo(self.client, 'sha256sum ' + shlex.quote(source)).split()[0]
        if sha(target) != remote_hash:
            raise RuntimeError('Board file changed during snapshot: ' + source)
        self.files.append({'path': relative.as_posix(), 'source': 'z15:' + source,
                           'sha256': remote_hash, 'bytes': target.stat().st_size,
                           'linux_mode': oct(stat.S_IMODE(before.st_mode))})


def audit_fpga(project):
    xpr = ET.parse(project / (PROJECT_NAME + '.xpr')).getroot()
    substitutions = {'$PPRDIR': str(project), '$PSRCDIR': str(project / (PROJECT_NAME + '.srcs')),
                     '$PGENDIR': str(project / (PROJECT_NAME + '.gen'))}
    references = []
    for file in xpr.findall('./FileSets/FileSet/File'):
        original = file.attrib['Path']
        resolved = original
        for key, value in substitutions.items():
            resolved = resolved.replace(key, value)
        references.append({'declared': original, 'exists': Path(resolved).is_file()})
    ip_files = []
    ns = {'s': 'http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009'}
    for component in sorted((project / 'ip_repo').glob('*/component.xml')):
        for file in ET.parse(component).findall('.//s:fileSets/s:fileSet/s:file/s:name', ns):
            path = component.parent / file.text
            ip_files.append({'component': component.relative_to(project).as_posix(),
                             'file': file.text, 'exists': path.is_file()})
    if not references or not ip_files or not all(x['exists'] for x in references + ip_files):
        raise RuntimeError('FPGA project contains missing source dependencies')
    return {'project_references': references, 'custom_ip_references': ip_files,
            'source_dependency_audit': 'passed', 'fresh_synthesis_this_run': False}


def board_snapshot(bundle, client):
    bundle.client = client
    base = Path('board_snapshot/rootfs')
    commands = {
        'kernel': 'uname -r', 'architecture': 'uname -m',
        'boot_id': 'cat /proc/sys/kernel/random/boot_id',
        'startup': 'cat /run/guardianloop-startup/status.json',
        'services': 'systemctl show ' + ' '.join(UNITS) +
                    ' -p Id -p FragmentPath -p DropInPaths -p ActiveState -p SubState -p ExecStart -p EnvironmentFiles',
        'enabled': 'systemctl is-enabled ' + ' '.join(UNITS),
        'modules': 'lsmod', 'network': 'ip -br addr',
    }
    evidence = {name: command(client, cmd).strip() for name, cmd in commands.items()}
    evidence['optional_files_absent'] = []
    with client.open_sftp() as sftp:
        manifest_path = PROD + '/release_manifest.json'
        with sftp.open(manifest_path) as stream:
            manifest = json.loads(stream.read())
        files = list(manifest['files']) + ['release_manifest.json']
        for name in files:
            bundle.remote(sftp, PROD + '/' + name, base / PROD.lstrip('/') / name)
        app = bundle.root / base / PROD.lstrip('/')
        for name, expected in manifest['files'].items():
            if sha(app / name) != expected:
                raise RuntimeError('Installed board release is not consistent: ' + name)
        evidence['release_manifest'] = manifest
        evidence['runtime_release_verified'] = True
        # Extra support files are not substituted for the verified runtime.
        extras = ('board_check.py', 'cyton_usb_probe.py', 'probe_cyton_raw.py',
                  'verify_covariance_board.py', 'seed_shadow_replay.py', 'gameemo_emotion_model.json',
                  '8188eu.ko', 'r8188eu.ko', 'lib80211.ko', 'rtl8188eufw.bin',
                  'rtl8188eu-linux-v5.4.tar.gz')
        present = set(sftp.listdir(PROD))
        for name in extras:
            if name in present:
                bundle.remote(sftp, PROD + '/' + name, base / PROD.lstrip('/') / name)
        for name in UNITS:
            path = '/etc/systemd/system/' + name
            bundle.remote(sftp, path, base / path.lstrip('/'))
            folder = path + '.d'
            try:
                entries = sftp.listdir(folder)
            except FileNotFoundError:
                entries = []
            for entry in entries:
                if entry.endswith('.conf'):
                    bundle.remote(sftp, folder + '/' + entry, base / folder.lstrip('/') / entry)
        configs = ['/etc/default/guardianloop-cyton', '/etc/guardianloop/ap.conf',
                   '/etc/guardianloop/dnsmasq.conf', '/etc/network/interfaces', '/etc/modules']
        for directory in ('/etc/NetworkManager/conf.d', '/etc/modprobe.d', '/etc/modules-load.d'):
            for name in sftp.listdir(directory):
                if 'guardianloop' in name or '8188' in name:
                    configs.append(directory + '/' + name)
        for path in configs:
            try:
                sftp.stat(path)
            except FileNotFoundError:
                evidence['optional_files_absent'].append(path)
                continue
            bundle.remote(sftp, path, base / path.lstrip('/'))
        for name in ('BOOT.BIN', 'image.ub', 'boot.scr', 'boot.py', 'REVISION'):
            path = '/boot/' + name
            try:
                sftp.stat(path)
            except FileNotFoundError:
                evidence['optional_files_absent'].append(path)
                continue
            bundle.remote(sftp, path, base / path.lstrip('/'))
        bundle.remote(sftp, '/sys/firmware/fdt', Path('board_snapshot/current_kernel.dtb'))
    # Metadata only; do not export private URLs from pip's direct-install records.
    names = ['numpy', 'scipy', 'pynq', 'scikit-learn', 'joblib', 'pyserial', 'psutil', 'notebook']
    code = 'import importlib.metadata as m,json; wanted=' + repr(names) + ';' + \
           ' found={d.metadata["Name"].lower():d.version for d in m.distributions()};' + \
           ' print(json.dumps({n:found.get(n) for n in wanted},sort_keys=True))'
    evidence['python_packages'] = json.loads(command(client,
        '/usr/local/share/pynq-venv/bin/python3 -c ' + shlex.quote(code)))
    return evidence


def build(output):
    output.mkdir(parents=True, exist_ok=False)
    bundle = Bundle(output)
    client = connect()
    try:
        evidence = board_snapshot(bundle, client)
    finally:
        client.close()
    print('BOARD_SNAPSHOT_VERIFIED', flush=True)
    project = Path('projects/ican_fpga_project') / PROJECT_NAME
    bundle.local(FPGA / (PROJECT_NAME + '.xpr'), project / (PROJECT_NAME + '.xpr'))
    for folder in (PROJECT_NAME + '.srcs', 'ip_repo', 'tcl', 'docs', 'reports'):
        bundle.tree(FPGA / folder, project / folder, generated_bd_ip=folder.endswith('.srcs'))
    wrapper = Path(PROJECT_NAME + '.gen/sources_1/bd/guardianloop_bd/hdl')
    bundle.tree(FPGA / wrapper, project / wrapper)
    bit = FPGA / (PROJECT_NAME + '.runs/impl_1/guardianloop_bd_wrapper.bit')
    hwh = FPGA / (PROJECT_NAME + '.gen/sources_1/bd/guardianloop_bd/hw_handoff/guardianloop_bd.hwh')
    if sha(bit) != EXPECTED_BIT or sha(hwh) != EXPECTED_HWH:
        raise RuntimeError('Local FPGA artifacts do not match the production board release')
    formal_app = output / 'board_snapshot/rootfs' / PROD.lstrip('/')
    if sha(formal_app / 'guardianloop_pynq.bit') != sha(bit) or sha(formal_app / 'guardianloop_pynq.hwh') != sha(hwh):
        raise RuntimeError('Board and FPGA project artifact pair mismatch')
    bundle.local(bit, Path('fpga_release/guardianloop_pynq.bit'))
    bundle.local(hwh, Path('fpga_release/guardianloop_pynq.hwh'))
    audit = audit_fpga(output / project)
    evidence['fpga'] = {'original_project': str(FPGA), 'bit_sha256': sha(bit),
                        'hwh_sha256': sha(hwh), 'matching_artifacts': True, **audit}
    print('FORMAL_FPGA_SOURCE_DEPENDENCIES_VERIFIED', flush=True)
    # Preserve the working tools, without datasets, recordings, build caches or history.
    dev = Path('projects/codex_project')
    for folder in ('pynq_guardianloop', 'eeg_apps_z15', 'viformer_z15'):
        for file in sorted((ROOT / folder).iterdir()):
            if file.is_file() and file.suffix.lower() in DEV_SUFFIXES:
                bundle.local(file, dev / folder / file.name)
    for folder in ('pl_filter_candidate', 'pl_filter_pipeline_candidate', 'pl_matrix_candidate'):
        bundle.tree(ROOT / 'eeg_apps_z15' / folder, dev / 'eeg_apps_z15' / folder, DEV_SUFFIXES)
    candidate = ROOT / 'gli26c/project'
    bundle.local(candidate / 'gl_filter_coexist_sc_20260929.xpr',
                 dev / 'gli26c/project/gl_filter_coexist_sc_20260929.xpr')
    for folder in ('gl_filter_coexist_sc_20260929.srcs',
                   'gl_filter_coexist_sc_20260929.gen/sources_1/bd/guardianloop_bd/hdl'):
        bundle.tree(candidate / folder, dev / 'gli26c/project' / folder,
                    generated_bd_ip=folder.endswith('.srcs'))
    for name in ('guardianloop_bd_wrapper.bit', 'guardianloop_bd_wrapper.hwh'):
        bundle.local(ROOT / 'gli26c/bit1' / name, dev / 'gli26c/bit1' / name)
    bundle.local(ROOT / 'eeg_apps_z15/output/pl_filter_v2025_2_20260927/coeff.hex',
                 dev / 'eeg_apps_z15/output/pl_filter_v2025_2_20260927/coeff.hex')
    selected = [
        'startup_deployment_20261001/RESULTS.md', 'startup_deployment_20261001/deployment.json',
        'startup_deployment_20261001/replay_audit.json', 'startup_deployment_20261001/after_replay.json',
        'ssvep_quality_gate_20260930/DEPLOY_RESULTS.md',
        'pl_integrated_smartconnect_20260929/RESULTS.md',
        'pl_integrated_candidate_20260929/PL_PAIRED_GATE_RESULT_20260930.md',
        'pl_integrated_candidate_20260929/PL_PAIRED_GATE_PLAN_20260930.md',
    ]
    for name in selected:
        bundle.local(ROOT / 'eeg_apps_z15/output' / name, dev / 'eeg_apps_z15/output' / name)
    bundle.local(ROOT / 'pynq_guardianloop/DEPLOYMENT.md', Path('docs/CURRENT_DEPLOYMENT.md'))
    reference = ROOT / 'output/team_handoff_templates'
    bundle.local(reference / 'README.md', Path('README.md'))
    bundle.local(reference / 'prepare_formal_project.tcl', project / 'prepare_formal_project.tcl')
    comparisons = {}
    manifest = evidence['release_manifest']
    for name, deployed in manifest['files'].items():
        local = ROOT / 'pynq_guardianloop' / name
        comparisons[name] = {'board_sha256': deployed, 'local_present': local.is_file(),
                             'local_matches_board': sha(local) == deployed if local.is_file() else None}
    evidence['local_working_copy_comparison'] = comparisons
    evidence['snapshot_scope'] = 'Read-only board export; no service restart, PL load, synthesis, or boot writes.'
    evidence['omitted'] = ['training datasets', 'raw personal EEG', 'trial logs', 'SSH private keys',
                           'complete SD image', 'Vivado installation', 'unrelated historical builds']
    (output / 'PACKAGE_AUDIT.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (output / 'FILES_SHA256.json').write_text(json.dumps(bundle.files, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    entries = sorted(p for p in output.rglob('*') if p.is_file())
    checksums = ''.join(sha(p) + '  ' + p.relative_to(output).as_posix() + '\n' for p in entries)
    (output / 'SHA256SUMS.txt').write_text(checksums, encoding='utf-8')
    archive = output.with_suffix('.zip')
    if archive.exists():
        raise FileExistsError(archive)
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for path in sorted(output.rglob('*')):
            if path.is_file():
                zipped.write(path, (Path(output.name) / path.relative_to(output)).as_posix())
    with zipfile.ZipFile(archive) as zipped:
        if zipped.testzip() is not None:
            raise RuntimeError('Archive CRC failed')
        for line in checksums.splitlines():
            expected, name = line.split('  ', 1)
            if hashlib.sha256(zipped.read(output.name + '/' + name)).hexdigest() != expected:
                raise RuntimeError('Archive SHA-256 mismatch: ' + name)
        if len(zipped.namelist()) != len(entries) + 1:
            raise RuntimeError('Archive file count mismatch')
    archive_hash = sha(archive)
    archive.with_suffix('.zip.sha256').write_text(archive_hash + '  ' + archive.name + '\n', encoding='utf-8')
    print(json.dumps({'archive': str(archive), 'bytes': archive.stat().st_size,
                      'files': len(entries) + 1, 'sha256': archive_hash,
                      'source_dependencies': 'passed', 'archive_crc_and_sha256': 'passed'}, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'handoff' /
                        ('GL_Z15_' + datetime.now().strftime('%Y%m%d_%H%M%S')))
    build(parser.parse_args().output)
