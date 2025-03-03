import contextlib
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import IO, AnyStr

from dataclasses_json import config, dataclass_json

log = logging.getLogger("drakrun")

hexstring = config(
    encoder=lambda v: hex(v),
    decoder=lambda v: int(v, 16),
)


@dataclass_json
@dataclass
class VmiOffsets:
    # Fields correspond to output defined in
    # https://github.com/libvmi/libvmi/blob/master/examples/win-offsets.c

    win_ntoskrnl: int = field(metadata=hexstring)
    win_ntoskrnl_va: int = field(metadata=hexstring)

    win_tasks: int = field(metadata=hexstring)
    win_pdbase: int = field(metadata=hexstring)
    win_pid: int = field(metadata=hexstring)
    win_pname: int = field(metadata=hexstring)
    win_kdvb: int = field(metadata=hexstring)
    win_sysproc: int = field(metadata=hexstring)
    win_kpcr: int = field(metadata=hexstring)
    win_kdbg: int = field(metadata=hexstring)

    kpgd: int = field(metadata=hexstring)

    @staticmethod
    def from_tool_output(output: str) -> 'VmiOffsets':
        """
        Parse vmi-win-offsets tool output and return VmiOffsets.
        If any of the fields is missing, throw TypeError
        """
        offsets = re.findall(r'^([a-z_]+):(0x[0-9a-f]+)$', output, re.MULTILINE)
        vals = {k: int(v, 16) for k, v in offsets}
        return VmiOffsets(**vals)


@dataclass_json
@dataclass
class RuntimeInfo:
    vmi_offsets: VmiOffsets
    inject_pid: int

    def load(file_obj: IO[AnyStr]) -> 'RuntimeInfo':
        return RuntimeInfo.from_json(file_obj.read())


def patch_config(cfg):
    try:
        access_key = cfg.config['minio']['access_key']
        secret_key = cfg.config['minio']['secret_key']
    except KeyError:
        sys.stderr.write('WARNING! Misconfiguration: section [minio] of config.ini doesn\'t contain access_key or secret_key.\n')
        return cfg

    if not access_key and not secret_key:
        if not os.path.exists('/etc/drakcore/minio.env'):
            raise RuntimeError('ERROR! MinIO access credentials are not configured (and can not be auto-detected), unable to start.\n')

        with open('/etc/drakcore/minio.env', 'r') as f:
            minio_cfg = [line.strip().split('=', 1) for line in f if line.strip() and '=' in line]
            minio_cfg = {k: v for k, v in minio_cfg}

        try:
            cfg.config['minio']['access_key'] = minio_cfg['MINIO_ACCESS_KEY']
            cfg.config['minio']['secret_key'] = minio_cfg['MINIO_SECRET_KEY']
        except KeyError:
            sys.stderr.write('WARNING! Misconfiguration: minio.env doesn\'t contain MINIO_ACCESS_KEY or MINIO_SECRET_KEY.\n')

    return cfg


def get_domid_from_instance_id(instance_id: int) -> int:
    output = subprocess.check_output(["xl", "domid", f"vm-{instance_id}"])
    return int(output.decode('utf-8').strip())


def get_xl_info():
    xl_info_out = subprocess.check_output(['xl', 'info']).decode('utf-8', 'replace')
    xl_info_lines = xl_info_out.strip().split('\n')

    cfg = {}

    for line in xl_info_lines:
        k, v = line.split(':', 1)
        k, v = k.strip(), v.strip()
        cfg[k] = v

    return cfg


def get_xen_commandline(parsed_xl_info):
    opts = parsed_xl_info['xen_commandline'].split(' ')

    cfg = {}

    for opt in opts:
        if not opt.strip():
            continue

        if '=' not in opt:
            cfg[opt] = '1'
        else:
            k, v = opt.split('=', 1)
            cfg[k] = v

    return cfg


def safe_delete(file_path) -> bool:
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"Deleted {file_path}")
        else:
            logging.info(f"Already deleted {file_path}")
        return True
    except OSError as e:
        logging.warning(f"{e.filename}: {e.strerror}")
        return False


@contextlib.contextmanager
def graceful_exit(proc: subprocess.Popen):
    try:
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired as err:
            log.error("Process %s doesn't exit after timeout.", err.cmd)
            proc.kill()
            proc.wait()
            log.error("Process was forceully killed")
