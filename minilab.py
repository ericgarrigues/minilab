#!/usr/bin/python

"""
Minilab is a network lab simulator based on
mininet. Its goal is to provide an easy way
to setup and test any kind of complex network.

"""

import subprocess
import shutil
import shlex
import argparse
import yaml
import os
import sys
import glob

from mininet.net import Mininet
from mininet.node import Host, OVSSwitch, RemoteController
from mininet.log import setLogLevel, info
from mininet.cli import CLI

from jinja2 import FileSystemLoader, Environment

from nat import *


class ManageableHost(Host):
    def __init__(self, name, ip=None, inNamespace=True,
                 root_dir=None, ssh_template=None,
                 auth_keys=None, **kwargs):

        self.name = name
        self.ssh_template = ssh_template
        self.auth_keys = auth_keys
        self.root_dir = root_dir
        self.ssh_pid_file = None
        self.mounted_dirs = []

        Host.__init__(self, name, inNamespace, **kwargs)

    def list_processes(self):
        process_list = []
        my_ns_symlink = '/proc/%s/ns/net' % self.pid
        for symlink in glob.glob('/proc/[1-9]*/ns/net'):
            pid = None
            try:
                if os.path.samefile(my_ns_symlink, symlink):
                    pid = symlink.split('/')[2]
            except:
                pass
            else:
                if pid and int(pid) != self.pid:
                    process_list.append(pid)

        return process_list

    def stop_all_processes(self):
        info('**** Stopping all remaining processes on %s\n' % self.name)
        running_processes = self.list_processes()

        for process in running_processes:
            cmd = "kill -9 %s" % process
            info('**** killing process id %s\n' % process)
            subprocess.call(shlex.split(cmd))

    def stop_processes(self):
        self.stop_ssh_server()
        self.stop_all_processes()

    def create_ssh_config(self):
        self.ssh_pid_file = os.path.join(self.root_dir, "var", "run",
                                         "sshd.pid")

        return self.ssh_template.render(pid_file=self.ssh_pid_file,
                                        host_dir=self.root_dir)

    def copy_auth_keys(self):
        ssh_dir = os.path.join(self.root_dir, 'root/.ssh')
        if not os.path.exists(ssh_dir):
            os.mkdir(ssh_dir, 0700)

        key_file = open(self.auth_keys)
        destination = open(os.path.join(ssh_dir, 'authorized_keys'), 'wb')
        destination.write(key_file.read())
        destination.close()
        key_file.close()

    def start_ssh_server(self):
        if self.auth_keys:
            self.copy_auth_keys()

        ssh_config = self.create_ssh_config()
        host_config_path = os.path.join(self.root_dir,
                                        'etc/ssh/sshd_config')

        sshf = open(host_config_path, 'wb')
        sshf.write(ssh_config)
        sshf.close()

        info('**** Starting ssh server on %s\n' % self.name)
        start_ssh = '/usr/sbin/sshd -f %s' % host_config_path
        self.cmd(shlex.split(start_ssh))

    def stop_ssh_server(self):
        info('**** Stopping ssh server on %s\n' % self.name)
        kill_ssh = "/bin/kill $(cat %s)" % self.ssh_pid_file
        self.cmd(shlex.split(kill_ssh))

    def clean_all(self):
        pass


def mount_root_fs(hostname, lab_dir, root_fs):
    info('**** Mounting filesystem for %s\n' % hostname)
    if not os.path.exists(lab_dir):
        os.mkdir(lab_dir)

    host_dir = os.path.join(lab_dir, hostname)
    work_dir = os.path.join(host_dir, 'work')
    upper_dir = os.path.join(host_dir, 'upper')
    merged_dir = os.path.join(host_dir, 'merged')

    if not os.path.exists(host_dir):
        os.mkdir(host_dir)
        os.mkdir(work_dir)
        os.mkdir(upper_dir)
        os.mkdir(merged_dir)

    cmd = "mount -t overlay overlay -o lowerdir=%s,upperdir=%s,workdir=%s %s" % \
          (root_fs, upper_dir, work_dir, merged_dir)

    mount_root = shlex.split(cmd)
    subprocess.call(mount_root)

    host_proc = os.path.join(merged_dir, 'proc')
    cmd_p = "mount -t proc proc %s" % host_proc
    mount_proc = shlex.split(cmd_p)
    subprocess.call(mount_proc)

    host_sys = os.path.join(merged_dir, 'sys')
    cmd_s = "mount -t sysfs sysfs %s" % host_sys
    mount_sys = shlex.split(cmd_s)
    subprocess.call(mount_sys)

    return merged_dir


def umount_root_fs(hostname, lab_dir):
    info('**** Unmounting filesystem for %s\n' % hostname)

    host_dir = os.path.join(lab_dir, hostname)
    merged_dir = os.path.join(host_dir, 'merged')
    host_proc = os.path.join(merged_dir, 'proc')
    host_sys = os.path.join(merged_dir, 'sys')

    for mount_point in [host_sys, host_proc, merged_dir]:
        subprocess.call(shlex.split("umount %s" % mount_point))

    # fixme: currently need to umount /sys
    # subprocess.call(shlex.split("umount %s" % '/sys'))


def load_config(config_file):
    cfg = open(config_file)
    config = yaml.load(cfg)
    cfg.close()

    return config


def setup_controllers(net, topology):
    for controller in topology['controllers']:
        ctrl = RemoteController(controller['name'],
                                ip=controller['ip'],
                                port=controller['port'])
        info('*** Adding controller\n')
        net.addController(ctrl)


def setup_hosts(net, switches, config, topology):
    info('*** Adding hosts\n')
    hosts = {}

    ssh_template = None
    auth_keys = None

    if 'ssh' in config:
        template = config['ssh']['template']
        tmpl_dir = config['ssh']['tmpl_dir']

        env = Environment(loader=FileSystemLoader(tmpl_dir))
        ssh_template = env.get_template(template)
        if 'authorized_keys' in config['ssh']:
            auth_keys = config['ssh']['authorized_keys']

    for host in topology['hosts']:
        if host['is_manageable']:
            root_dir = mount_root_fs(host['name'], config['ml_dir'],
                                     config['rootfs'])
            new_host = net.addHost(host['name'], ip=None,
                                   cls=ManageableHost,
                                   root_dir=root_dir,
                                   ssh_template=ssh_template,
                                   auth_keys=auth_keys)
        else:
            new_host = net.addHost(host['name'])

        for link in host['links']:
            switch = switches[link['sw']]
            lnk = net.addLink(new_host, switch)

            if 'ip' in link:
                ip, netmask = link['ip'].split('/')
                new_host.setIP(ip, prefixLen=netmask, intf=lnk.intf1)

        if 'gw' in host:
            new_host.sendCmd('ip route add default via %s' % host['gw'])
            new_host.waiting = False

        if not host['name'] in hosts:
            hosts[host['name']] = {'node': new_host, 'rootfs': new_host.name}

    return hosts


def setup_switches(net, topology):
    switches = {}
    info('*** Adding switches\n')
    # first loop : create switches
    for switch in topology['switches']:
        if 'protocols' in switch:
            protocols = ','.join(switch['protocols'])
        else:
            protocols = 'OpenFlow10'

        switches[switch['name']] = net.addSwitch(switch['name'],
                                                 dpid=switch['dpid'],
                                                 cls=OVSSwitch,
                                                 protocols=protocols)
    # second loop: add links between switches
    for switch in topology['switches']:
        if 'links' in switch:
            for peer in switch['links']:
                net.addLink(switches[switch['name']],
                            switches[peer])

    return switches


def setup_nat(net, topology):
    node = None
    if 'nat' in topology:
        info('*** Setup nat gateway node\n')
        node = connectToInternet(net,
                                 switch=topology['nat']['switch']['name'],
                                 node_name=topology['nat']['node']['name'],
                                 ip_address=topology['nat']['node']['ip'])

        info('** Starting nat\n')
        startNAT(node,
                 inetIntf=topology['nat']['ext_iface'],
                 intIP=topology['nat']['node']['ip'])

    return node


def fix_switch_protocols(topology):
    """ force protocols versions as mininet < 2.2.0 is not doing its job"""

    for switch in topology['switches']:
        if 'protocols' in switch:
            protocols = ','.join(switch['protocols'])
        else:
            protocols = 'OpenFlow10'

        cmd = "ovs-vsctl set Bridge %s protocols=%s" % (switch['name'],
                                                        protocols)
        subprocess.call(shlex.split(cmd))


def set_oob_switch_standalone(topology):
    if 'nat' in topology:
        switch = topology['nat']['switch']['name']
        cmd = shlex.split("ovs-vsctl set-fail-mode %s standalone " % switch)
        subprocess.call(cmd)

        cmd2 = shlex.split("ovs-vsctl del-controller %s" % switch)
        subprocess.call(cmd2)


def tear_down_nat(node):
    info('** Stopping nat\n')
    stopNAT(node)


def start(net, topology):
    for name, node in net.items():
        if isinstance(node, ManageableHost):
            node.start_ssh_server()

    info('** Starting network\n')
    net.start()

    fix_switch_protocols(topology)
    set_oob_switch_standalone(topology)

    CLI(net)


def stop(net, config):
    for name, node in net.items():
        if isinstance(node, ManageableHost):
            node.stop_processes()
            umount_root_fs(name, config['ml_dir'])

    info('** Stopping network\n')
    net.stop()


def setup_topo(config, topology):
    nat_node = None

    try:
        net = Mininet(controller=RemoteController)

        setup_controllers(net, topology)
        switches = setup_switches(net, topology)
        setup_hosts(net, switches, config, topology)

        nat_node = setup_nat(net, topology)

        start(net, topology)

    except Exception, e:
        info('** Error spawning topology\n')
        print e
        cleanup_all(config, topology)
        sys.exit(1)

    if nat_node:
        tear_down_nat(nat_node)

    stop(net, config)


def cleanup_all(config, topology, hard_cleanup=False):
    for host in topology['hosts']:
        if host['is_manageable']:
            host_dir = os.path.join(config['ml_dir'], host['name'])
            host_root_dir = os.path.join(host_dir, 'merged')
            for directory in ['sys', 'proc']:
                mount_point = os.path.join(host_root_dir, directory)
                subprocess.call(shlex.split("umount %s" % mount_point))

            subprocess.call(shlex.split("umount %s" % host_root_dir))

            if hard_cleanup:
                shutil.rmtree(host_dir)

    # clean mininet
    subprocess.call(shlex.split("mn -c"))


if __name__ == '__main__':
    setLogLevel('info')

    parser = argparse.ArgumentParser(description='Minilab arguments.')
    parser.add_argument('--config', dest='config', type=str,
                        default='config.yaml',
                        help='minilab config file (default: config.yaml)')
    parser.add_argument('topology', metavar='topology', type=str,
                        help='topology configuration file')
    parser.add_argument('--cleanup', dest='cleanup', action='store_true',
                        help='cleanup minilab setup')
    parser.add_argument('--reset', dest='hard_cleanup', action='store_true',
                        help='cleanup and destroy all hosts directories')

    args = parser.parse_args()

    minilab_config = load_config(args.config)
    topo_config = load_config(args.topology)
    cleanup = args.cleanup

    if args.cleanup:
        if args.hard_cleanup:
            info('** Cleaning minilab from scratch\n')
            cleanup_all(minilab_config, topo_config, hard_cleanup=True)
        else:
            info('** Cleaning minilab\n')
            cleanup_all(minilab_config, topo_config)

        info('** Cleaning done\n')
        sys.exit(0)

    setup_topo(minilab_config, topo_config)
